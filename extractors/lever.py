from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class LeverExtractor(BaseExtractor):
    provider = "lever"
    api_url_template = "https://api.lever.co/v0/postings/{board_token}?mode=json&limit={limit}&offset={offset}"
    page_limit = 250
    pagination_delay_seconds = 1.0

    def extract(self) -> list[JobListing]:
        payload = self._fetch_all_pages()
        listings: list[JobListing] = []

        for job in payload:
            if not isinstance(job, dict):
                raise ExtractionError("Lever job payload is not an object", raw_payload=job)

            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error(
                    "Failed mapping Lever job on board %s",
                    self.board_token,
                    exc_info=True,
                )
                raise ExtractionError("Malformed Lever job payload", raw_payload=job) from exc

        self.logger.info("Fetched %s Lever jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _fetch_all_pages(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        offset = 0

        while True:
            url = self.api_url_template.format(
                board_token=self.board_token,
                limit=self.page_limit,
                offset=offset,
            )
            payload = self._get_json(url)
            if not isinstance(payload, list):
                self.logger.error("Unexpected Lever payload shape for board %s", self.board_token)
                raise ExtractionError("Unexpected Lever payload schema", raw_payload=payload)
            if not payload:
                break

            jobs.extend(payload)
            if len(payload) < self.page_limit:
                break

            offset += self.page_limit
            time.sleep(self.pagination_delay_seconds)

        return jobs

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        categories = job.get("categories") if isinstance(job.get("categories"), dict) else {}
        job_id = self._required_string(job, "id")
        description_html = self._description_html(job)

        return self._build_listing(
            company_name=self._company_name(),
            job_title=self._required_string(job, "text"),
            job_url=self._required_string(job, "hostedUrl"),
            ats_job_id=job_id,
            location=self._locations(categories),
            raw_description=self._raw_description(job),
            description_html=description_html or None,
            employment_type=str(categories.get("commitment")).strip() if categories.get("commitment") else None,
            departments=self._departments(categories),
            date_posted=self._parse_datetime(job.get("createdAt")),
        )

    def _company_name(self) -> str:
        return self.board_token.replace("-", " ").title()

    def _locations(self, categories: dict[str, Any]) -> list[str]:
        return self._string_list(categories.get("location")) or ["Unspecified"]

    def _departments(self, categories: dict[str, Any]) -> list[str]:
        departments: list[str] = []
        for key in ("team", "department"):
            value = categories.get(key)
            if value:
                departments.extend(self._string_list(value))
        return departments

    def _raw_description(self, job: dict[str, Any]) -> str:
        description_parts = [
            job.get("descriptionPlain"),
            job.get("additionalPlain"),
        ]

        lists = job.get("lists")
        if isinstance(lists, list):
            for section in lists:
                if not isinstance(section, dict):
                    continue
                heading = section.get("text")
                content = section.get("content")
                if heading:
                    description_parts.append(str(heading))
                if content:
                    description_parts.append(str(content))

        return "\n\n".join(html_to_text(part) for part in description_parts if part).strip()

    def _description_html(self, job: dict[str, Any]) -> str:
        description_parts = [job.get("description"), job.get("additional")]

        lists = job.get("lists")
        if isinstance(lists, list):
            for section in lists:
                if isinstance(section, dict) and section.get("content"):
                    description_parts.append(section["content"])

        return "\n\n".join(str(part).strip() for part in description_parts if part)
