from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class AmazonExtractor(BaseExtractor):
    provider = "amazon"
    api_url_template = (
        "https://www.amazon.jobs/en/search.json"
        "?offset={offset}&result_limit={limit}&sort=relevant"
    )
    page_limit = 100
    max_pages = 120
    supplemental_categories = [
        "software-development",
        "machine-learning-science",
        "data-science",
        "database-administration",
        "operations-it-support-engineering",
        "systems-quality-security-engineering",
        "solutions-architect",
        "project-program-product-management-technical",
        "hardware-development",
        "business-intelligence",
    ]

    def extract(self) -> list[JobListing]:
        payload = self._fetch_all_pages()
        listings: list[JobListing] = []

        for job in payload:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping Amazon job", exc_info=True)
                raise ExtractionError("Malformed Amazon job payload", raw_payload=job) from exc

        self.logger.info("Fetched %s Amazon jobs", len(listings), extra={"company": "Amazon"})
        return listings

    def _fetch_all_pages(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        general_jobs, hits = self._fetch_pages(seen_ids=seen_ids)
        jobs.extend(general_jobs)

        if hits is not None and hits >= 10_000:
            for category in self.supplemental_categories:
                supplemental_jobs, _ = self._fetch_pages(
                    seen_ids=seen_ids,
                    extra_query={"category[]": category},
                )
                jobs.extend(supplemental_jobs)

        return jobs

    def _fetch_pages(
        self,
        *,
        seen_ids: set[str],
        extra_query: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], int | None]:
        jobs: list[dict[str, Any]] = []
        total: int | None = None

        for page in range(self.max_pages):
            offset = page * self.page_limit
            url = self._page_url(offset, self.page_limit, extra_query)
            payload = self._get_json(url)
            if not isinstance(payload, dict):
                raise ExtractionError("Unexpected Amazon jobs payload schema", raw_payload=payload)

            if total is None and isinstance(payload.get("hits"), int):
                total = int(payload["hits"])

            raw_jobs = payload.get("jobs")
            if not isinstance(raw_jobs, list):
                if payload.get("error"):
                    break
                raise ExtractionError("Unexpected Amazon jobs payload schema", raw_payload=payload)

            page_jobs = [job for job in raw_jobs if isinstance(job, dict)]
            if not page_jobs:
                break

            new_jobs: list[dict[str, Any]] = []
            for job in page_jobs:
                job_id = str(job.get("id_icims") or job.get("job_path") or job.get("title") or "").strip()
                if job_id and job_id in seen_ids:
                    continue
                if job_id:
                    seen_ids.add(job_id)
                new_jobs.append(job)

            if not new_jobs:
                break

            jobs.extend(new_jobs)
            if total is not None and len(jobs) >= total:
                break
            if len(page_jobs) < self.page_limit:
                break

        return jobs, total

    def _page_url(
        self,
        offset: int,
        limit: int,
        extra_query: dict[str, str] | None = None,
    ) -> str:
        url = self.api_url_template.format(offset=offset, limit=limit)
        if not extra_query:
            return url
        return f"{url}&{urlencode(extra_query, doseq=True)}"

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        job_id = str(job.get("id_icims") or job.get("job_path") or job["title"]).strip()
        description_html = "\n\n".join(
            str(value)
            for value in (
                job.get("description"),
                job.get("basic_qualifications"),
                job.get("preferred_qualifications"),
            )
            if value
        )

        return self._build_listing(
            company_name="Amazon",
            job_title=self._required_string(job, "title"),
            job_url=self._job_url(job),
            ats_job_id=job_id,
            location=self._locations(job),
            raw_description=html_to_text(description_html),
            description_html=description_html or None,
            employment_type=self._optional_string(job.get("job_type")),
            departments=self._string_list(job.get("team") or job.get("business_category")),
            date_posted=self._parse_datetime(job.get("posted_date")),
        )

    def _job_url(self, job: dict[str, Any]) -> str:
        job_path = job.get("job_path")
        if isinstance(job_path, str) and job_path.strip():
            return f"https://www.amazon.jobs{job_path}"
        return self._required_string(job, "url_next_step")

    def _locations(self, job: dict[str, Any]) -> list[str]:
        locations = self._string_list(job.get("normalized_location") or job.get("location"))
        return locations or ["Unspecified"]

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
