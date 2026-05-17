from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class SmartRecruitersExtractor(BaseExtractor):
    provider = "smartrecruiters"
    api_url_template = "https://api.smartrecruiters.com/v1/companies/{board_token}/postings"
    page_limit = 100
    max_pages = 20

    def extract(self) -> list[JobListing]:
        jobs = self._fetch_all_jobs()
        listings: list[JobListing] = []

        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping SmartRecruiters job", exc_info=True)
                raise ExtractionError("Malformed SmartRecruiters job payload", raw_payload=job) from exc

        if not listings:
            raise ExtractionError("No SmartRecruiters jobs discovered")

        self.logger.info("Fetched %s SmartRecruiters jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _fetch_all_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        offset = 0

        for _ in range(self.max_pages):
            payload = self._get_json(
                f"{self.api_url_template.format(board_token=self.board_token)}"
                f"?limit={self.page_limit}&offset={offset}"
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
                raise ExtractionError("Unexpected SmartRecruiters jobs payload schema", raw_payload=payload)

            page_jobs = [job for job in payload["content"] if isinstance(job, dict)]
            if not page_jobs:
                break
            jobs.extend(page_jobs)

            offset += len(page_jobs)
            total = payload.get("totalFound")
            if isinstance(total, int) and offset >= total:
                break
            if len(page_jobs) < self.page_limit:
                break

        return jobs

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        company = job.get("company") if isinstance(job.get("company"), dict) else {}
        department = job.get("department") if isinstance(job.get("department"), dict) else {}
        function = job.get("function") if isinstance(job.get("function"), dict) else {}
        employment = job.get("typeOfEmployment") if isinstance(job.get("typeOfEmployment"), dict) else {}
        description = " | ".join(
            part
            for part in [
                self._required_string(job, "name"),
                self._location(job),
                str(department.get("label") or ""),
                str(function.get("label") or ""),
            ]
            if part
        )

        return self._build_listing(
            company_name=str(company.get("name") or self.board_token).strip(),
            job_title=self._required_string(job, "name"),
            job_url=self._job_url(job),
            ats_job_id=self._required_string(job, "id"),
            location=[self._location(job)],
            raw_description=html_to_text(description),
            description_html=None,
            employment_type=self._optional_string(employment.get("label")),
            departments=[
                value
                for value in (
                    self._optional_string(department.get("label")),
                    self._optional_string(function.get("label")),
                )
                if value
            ],
            date_posted=self._parse_datetime(job.get("releasedDate")),
        )

    def _job_url(self, job: dict[str, Any]) -> str:
        posting_url = job.get("postingUrl")
        if isinstance(posting_url, str) and posting_url.strip():
            return posting_url.strip()
        return f"https://jobs.smartrecruiters.com/{self.board_token}/{self._required_string(job, 'id')}"

    def _location(self, job: dict[str, Any]) -> str:
        location = job.get("location")
        if isinstance(location, dict):
            full_location = location.get("fullLocation")
            if isinstance(full_location, str) and full_location.strip():
                return full_location.strip()
        return "Unspecified"

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
