from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class SuccessFactorsExtractor(BaseExtractor):
    provider = "successfactors"
    page_limit = 25
    max_pages = 300
    detail_workers = 8

    def extract(self) -> list[JobListing]:
        jobs = self._fetch_all_jobs()
        jobs = self._enrich_jobs_from_detail_pages(jobs)
        listings: list[JobListing] = []

        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping SuccessFactors job", exc_info=True)
                raise ExtractionError("Malformed SuccessFactors job payload", raw_payload=job) from exc

        if not listings:
            raise ExtractionError("No SuccessFactors jobs discovered")

        self.logger.info("Fetched %s SuccessFactors jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _fetch_all_jobs(self) -> list[dict[str, Any]]:
        if not self.source_url:
            raise ExtractionError("SuccessFactors extraction requires the original source URL")

        jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        base_url = "https://jobs.sap.com"

        for page in range(self.max_pages):
            url = f"{base_url}/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow={page * self.page_limit}"
            response = self.session.get(url, headers=self._headers(), timeout=self.timeout_seconds)
            response.raise_for_status()
            page_jobs = self._jobs_from_html(response.text, base_url, seen_urls)
            if not page_jobs:
                break
            jobs.extend(page_jobs)
            if len(page_jobs) < self.page_limit:
                break

        return jobs

    def _jobs_from_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[dict[str, Any]] = []

        for row in soup.select("tr.data-row"):
            anchor = row.select_one("a.jobTitle-link[href]")
            if anchor is None:
                continue
            job_url = urljoin(base_url, str(anchor["href"]))
            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            location_node = row.select_one(".jobLocation")
            title = anchor.get_text(" ", strip=True)
            jobs.append(
                {
                    "id": job_url.rstrip("/").split("/")[-1],
                    "title": title,
                    "url": job_url,
                    "location": location_node.get_text(" ", strip=True) if location_node else "Unspecified",
                    "description": title,
                    "date_posted": None,
                    "departments": [],
                }
            )

        return jobs

    def _enrich_jobs_from_detail_pages(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched_by_url: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=self.detail_workers) as executor:
            futures = {executor.submit(self._detail_fields, job): job for job in jobs}
            for future in as_completed(futures):
                original = futures[future]
                try:
                    enriched = {**original, **future.result()}
                except Exception:
                    self.logger.warning("Failed fetching SuccessFactors detail page for %s", original.get("url"), exc_info=True)
                    enriched = original
                enriched_by_url[str(original["url"])] = enriched
        return [enriched_by_url.get(str(job["url"]), job) for job in jobs]

    def _detail_fields(self, job: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(
            self._required_string(job, "url"),
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        description_node = soup.select_one(".jobdescription, .job, .jobDisplay")
        date_node = soup.select_one('meta[itemprop="datePosted"]')
        department_node = soup.select_one('[data-careersite-propertyid="department"]')
        fields: dict[str, Any] = {}
        if description_node is not None:
            fields["description"] = str(description_node)
        if date_node is not None and date_node.get("content"):
            fields["date_posted"] = str(date_node["content"])
        if department_node is not None:
            fields["departments"] = [department_node.get_text(" ", strip=True)]
        return fields

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        description = str(job.get("description") or job["title"])
        return self._build_listing(
            company_name="SAP",
            job_title=self._required_string(job, "title"),
            job_url=self._required_string(job, "url"),
            ats_job_id=self._required_string(job, "id"),
            location=self._string_list(job.get("location")) or ["Unspecified"],
            raw_description=html_to_text(description),
            description_html=description if "<" in description else None,
            employment_type=None,
            departments=self._string_list(job.get("departments")),
            date_posted=self._parse_datetime(job.get("date_posted")),
        )
