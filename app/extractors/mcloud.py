from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.extractors.base import BaseExtractor, ExtractionError
from app.extractors.text import html_to_text
from app.models import JobListing


class MCloudJobsExtractor(BaseExtractor):
    provider = "mcloud"
    api_url = "https://jobsapi-google.m-cloud.io/api/job/search"
    company_name = "Home Depot"
    company_key = "companies/8454851f-07b7-4e4c-9b5f-00e0ffbfcb09"
    page_limit = 100
    max_pages = 300

    def extract(self) -> list[JobListing]:
        jobs = self._fetch_all_jobs()
        listings: list[JobListing] = []
        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.warning("Skipping malformed m-cloud job", exc_info=True)
                continue

        if not listings:
            raise ExtractionError("No m-cloud jobs discovered")

        self.logger.info("Fetched %s m-cloud jobs", len(listings), extra={"company": self.company_name})
        return listings

    def _fetch_all_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        total: int | None = None

        for page in range(self.max_pages):
            offset = page * self.page_limit
            payload = self._get_json(
                f"{self.api_url}?companyName={self.company_key}"
                f"&pageSize={self.page_limit}&offset={offset}"
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("searchResults"), list):
                raise ExtractionError("Unexpected m-cloud jobs payload schema", raw_payload=payload)

            if total is None and isinstance(payload.get("totalHits"), int):
                total = int(payload["totalHits"])

            page_jobs = [item.get("job") for item in payload["searchResults"] if isinstance(item, dict)]
            page_jobs = [job for job in page_jobs if isinstance(job, dict)]
            if not page_jobs:
                break

            for job in page_jobs:
                job_id = str(job.get("id") or job.get("ref") or "").strip()
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                jobs.append(job)

            if total is not None and offset + len(page_jobs) >= total:
                break

        return jobs

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        title = self._required_string(job, "title")
        description_html = self._optional_string(job.get("description"))
        job_id = str(job.get("id") or job.get("ref")).strip()
        location = ", ".join(
            part
            for part in (
                self._optional_string(job.get("primary_city")),
                self._optional_string(job.get("primary_state")),
                self._optional_string(job.get("primary_country")),
            )
            if part
        )

        return self._build_listing(
            company_name=self.company_name,
            job_title=title,
            job_url=self._required_string(job, "url"),
            ats_job_id=job_id,
            location=[location or "Unspecified"],
            raw_description=html_to_text(description_html or title),
            description_html=description_html,
            employment_type=self._optional_string(job.get("job_type") or job.get("employment_type")),
            departments=self._string_list(job.get("primary_category") or job.get("department")),
            date_posted=self._parse_datetime(job.get("open_date")),
        )

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
