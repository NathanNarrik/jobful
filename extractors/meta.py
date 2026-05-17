from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from bs4 import BeautifulSoup
from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class MetaExtractor(BaseExtractor):
    provider = "meta"
    search_url = "https://www.metacareers.com/jobsearch"
    graphql_url = "https://www.metacareers.com/api/graphql"
    search_doc_id = "26703205452636175"
    detail_workers = 8

    def extract(self) -> list[JobListing]:
        jobs = self._fetch_search_jobs()
        jobs = self._enrich_jobs_from_detail_pages(jobs)
        listings: list[JobListing] = []

        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping Meta job", exc_info=True)
                raise ExtractionError("Malformed Meta job payload", raw_payload=job) from exc

        if not listings:
            raise ExtractionError("No Meta jobs discovered")

        self.logger.info("Fetched %s Meta jobs", len(listings), extra={"company": "Meta"})
        return listings

    def _fetch_search_jobs(self) -> list[dict[str, Any]]:
        html = self._get_text(self.search_url)
        lsd = self._required_match(html, r'\["LSD",\[\],\{"token":"([^"]+)"')
        spin_r = self._required_match(html, r'"__spin_r":(\d+)')
        spin_b = self._required_match(html, r'"__spin_b":"([^"]+)"')
        spin_t = self._required_match(html, r'"__spin_t":(\d+)')
        hsi = self._required_match(html, r'"hsi":"([^"]+)"')

        variables = {
            "search_input": {
                "q": None,
                "divisions": [],
                "offices": [],
                "roles": [],
                "leadership_levels": [],
                "saved_jobs": [],
                "saved_searches": [],
                "sub_teams": [],
                "teams": [],
                "is_leadership": False,
                "is_remote_only": False,
                "sort_by_new": False,
                "page": 1,
                "results_per_page": None,
            }
        }
        response = self.session.post(
            self.graphql_url,
            data={
                "av": "0",
                "__user": "0",
                "__a": "1",
                "__req": "1",
                "__hsi": hsi,
                "__comet_req": "31",
                "fb_dtsg": "",
                "jazoest": self._jazoest(lsd),
                "lsd": lsd,
                "__spin_r": spin_r,
                "__spin_b": spin_b,
                "__spin_t": spin_t,
                "fb_api_caller_class": "RelayModern",
                "fb_api_req_friendly_name": "CareersJobSearchResultsV2DataQuery",
                "variables": json.dumps(variables, separators=(",", ":")),
                "server_timestamps": "true",
                "doc_id": self.search_doc_id,
            },
            headers={**self._meta_headers("*/*"), "Origin": "https://www.metacareers.com", "Referer": self.search_url, "x-fb-lsd": lsd},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        root = payload.get("data", {}).get("job_search_with_featured_jobs_v2", {})
        jobs = root.get("all_jobs")
        if not isinstance(jobs, list):
            raise ExtractionError("Unexpected Meta jobs payload schema", raw_payload=payload)
        return [job for job in jobs if isinstance(job, dict)]

    def _get_text(self, url: str) -> str:
        response = self.session.get(
            url,
            headers=self._meta_headers("text/html,application/xhtml+xml,*/*"),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.text

    def _meta_headers(self, accept: str) -> dict[str, str]:
        return {
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "Mozilla/5.0",
        }

    def _enrich_jobs_from_detail_pages(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched_by_id: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=self.detail_workers) as executor:
            futures = {executor.submit(self._detail_fields, job): job for job in jobs}
            for future in as_completed(futures):
                original = futures[future]
                try:
                    enriched = {**original, **future.result()}
                except Exception:
                    self.logger.warning(
                        "Failed fetching Meta detail page for %s",
                        original.get("id"),
                        exc_info=True,
                    )
                    enriched = original
                enriched_by_id[str(original["id"])] = enriched
        return [enriched_by_id.get(str(job["id"]), job) for job in jobs]

    def _detail_fields(self, job: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(
            self._job_url(self._required_string(job, "id")),
            headers=self._meta_headers("text/html,application/xhtml+xml,*/*"),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        schema = self._job_posting_schema(soup)
        if not schema:
            return {}
        return {
            "description": schema.get("description"),
            "date_posted": schema.get("datePosted"),
            "employment_type": schema.get("employmentType"),
        }

    def _job_posting_schema(self, soup: BeautifulSoup) -> dict[str, Any]:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.get_text(strip=True))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
                return payload
        return {}

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        description_html = str(job.get("description") or "")
        departments = self._string_list(job.get("teams")) + self._string_list(job.get("sub_teams"))
        description = description_html or " | ".join(
            part
            for part in [
                self._required_string(job, "title"),
                ", ".join(self._string_list(job.get("locations"))),
                ", ".join(departments),
            ]
            if part
        )

        return self._build_listing(
            company_name="Meta",
            job_title=self._required_string(job, "title"),
            job_url=self._job_url(self._required_string(job, "id")),
            ats_job_id=self._required_string(job, "id"),
            location=self._string_list(job.get("locations")) or ["Unspecified"],
            raw_description=html_to_text(description),
            description_html=description_html or None,
            employment_type=self._optional_string(job.get("employment_type")),
            departments=departments,
            date_posted=self._parse_datetime(job.get("date_posted")),
        )

    def _job_url(self, job_id: str) -> str:
        return f"https://www.metacareers.com/jobs/{job_id}/"

    def _required_match(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text)
        if match is None:
            raise ExtractionError("Could not find required Meta page token")
        return match.group(1)

    def _jazoest(self, lsd: str) -> str:
        return "2" + "".join(str(ord(char)) for char in lsd)

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
