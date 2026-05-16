from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class TalentBrewExtractor(BaseExtractor):
    provider = "talentbrew"
    max_pages = 300

    COMPANY_BY_HOST = {
        "careers.blackrock.com": "BlackRock",
        "jobs.citi.com": "Citi",
    }

    def extract(self) -> list[JobListing]:
        if not self.source_url:
            raise ExtractionError("TalentBrew extraction requires the original source URL")

        jobs = self._fetch_all_jobs()
        listings: list[JobListing] = []
        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping TalentBrew job on board %s", self.board_token, exc_info=True)
                raise ExtractionError("Malformed TalentBrew job payload", raw_payload=job) from exc

        self.logger.info("Fetched %s TalentBrew jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _fetch_all_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        first_page = self._fetch_page(1)
        total_pages = min(self._total_pages(first_page), self.max_pages)
        jobs.extend(self._jobs_from_html(first_page, seen_ids))

        for page in range(2, total_pages + 1):
            html = self._fetch_page(page)
            page_jobs = self._jobs_from_html(html, seen_ids)
            jobs.extend(page_jobs)

        if not jobs:
            raise ExtractionError("No TalentBrew jobs discovered")
        return jobs

    def _fetch_page(self, page: int) -> str:
        assert self.source_url is not None
        parsed = urlparse(self.source_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        url = urljoin(base_url, "/search-jobs" if page == 1 else f"/search-jobs/{page}")
        response = self.session.get(url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.text

    def _total_pages(self, html: str) -> int:
        soup = BeautifulSoup(html, "html.parser")
        result_section = soup.select_one("#search-results")
        if result_section and result_section.get("data-total-pages"):
            value = result_section["data-total-pages"]
            if str(value).isdigit():
                return int(value)
        return 1

    def _jobs_from_html(self, html: str, seen_ids: set[str]) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[dict[str, Any]] = []

        for anchor in soup.select("a.section3__search-results-a[href], a.sr-job-item__link[href]"):
            job_url = urljoin(self.source_url or "", str(anchor["href"]))
            job_id = str(anchor.get("data-job-id") or self._job_id_from_url(job_url)).strip()
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title_node = anchor.select_one(".section3__job-title")
            title = title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True)
            info = self._job_info(anchor)
            if not info:
                info = self._radancy_job_info(anchor)
            jobs.append(
                {
                    "id": job_id,
                    "title": title,
                    "url": job_url,
                    "locations": info.get("Location", []) + info.get("Additional Locations", []),
                    "departments": info.get("Team", []),
                    "description": " | ".join(
                        part
                        for part in [
                            title,
                            ", ".join(info.get("Location", [])),
                            ", ".join(info.get("Additional Locations", [])),
                            ", ".join(info.get("Team", [])),
                        ]
                        if part
                    ),
                }
            )

        return jobs

    def _job_info(self, anchor: Any) -> dict[str, list[str]]:
        info: dict[str, list[str]] = {}
        for row in anchor.select(".section3__job-information"):
            label_node = row.find("span")
            value_node = row.select_one(".section3__job-info")
            if not label_node or not value_node:
                continue
            label = label_node.get_text(" ", strip=True).rstrip(":")
            values = [value.strip() for value in re.split(r",|\|", value_node.get_text(" ", strip=True)) if value.strip()]
            info[label] = values
        return info

    def _radancy_job_info(self, anchor: Any) -> dict[str, list[str]]:
        item = anchor.find_parent("li")
        if item is None:
            return {}

        location_node = item.select_one(".sr-job-location")
        type_node = item.select_one(".sr-job-type")
        info: dict[str, list[str]] = {}
        if location_node:
            info["Location"] = [location_node.get_text(" ", strip=True)]
        if type_node:
            info["Team"] = [type_node.get_text(" ", strip=True)]
        return info

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        description = str(job.get("description") or job["title"])
        return self._build_listing(
            company_name=self._company_name(),
            job_title=self._required_string(job, "title"),
            job_url=self._required_string(job, "url"),
            ats_job_id=self._required_string(job, "id"),
            location=self._string_list(job.get("locations")) or ["Unspecified"],
            raw_description=html_to_text(description),
            description_html=None,
            employment_type=None,
            departments=self._string_list(job.get("departments")),
            date_posted=None,
        )

    def _company_name(self) -> str:
        if self.source_url:
            hostname = urlparse(self.source_url).hostname or ""
            if hostname in self.COMPANY_BY_HOST:
                return self.COMPANY_BY_HOST[hostname]
        return self.board_token.replace("-", " ").title()

    def _job_id_from_url(self, url: str) -> str:
        return url.rstrip("/").split("/")[-1]
