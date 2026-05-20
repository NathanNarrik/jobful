from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from app.extractors.base import BaseExtractor, ExtractionError
from app.extractors.text import html_to_text
from app.models import JobListing


class LeverExtractor(BaseExtractor):
    provider = "lever"
    full_api_url_template = "https://api.lever.co/v0/postings/{board_token}?mode=json"
    api_url_template = "https://api.lever.co/v0/postings/{board_token}?mode=json&limit={limit}&offset={offset}"
    page_limit = 250
    max_pages = 8
    pagination_delay_seconds = 0.25
    COMPANY_BY_TOKEN = {
        "houzz": "Houzz",
        "shieldai": "Shield AI",
        "sonatype": "Sonatype",
        "veeva": "Veeva Systems",
        "zilliz": "Zilliz",
        "zoox": "Zoox",
    }

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
        full_payload = self._get_json(self.full_api_url_template.format(board_token=self.board_token))
        if isinstance(full_payload, list):
            return self._new_jobs(full_payload, set())

        jobs: list[dict[str, Any]] = []
        seen_job_ids: set[str] = set()
        offset = 0
        page_count = 0

        while True:
            if page_count >= self.max_pages:
                self.logger.warning(
                    "Stopping Lever pagination for board %s after %s pages",
                    self.board_token,
                    self.max_pages,
                )
                break

            url = self.api_url_template.format(
                board_token=self.board_token,
                limit=self.page_limit,
                offset=offset,
            )
            payload = self._get_json(url)
            page_count += 1
            if not isinstance(payload, list):
                self.logger.error("Unexpected Lever payload shape for board %s", self.board_token)
                raise ExtractionError("Unexpected Lever payload schema", raw_payload=payload)
            if not payload:
                break

            new_jobs = self._new_jobs(payload, seen_job_ids)
            if not new_jobs:
                self.logger.warning(
                    "Stopping Lever pagination for board %s because offset %s returned no new jobs",
                    self.board_token,
                    offset,
                )
                break

            jobs.extend(new_jobs)
            if len(payload) < self.page_limit:
                break

            offset += self.page_limit
            time.sleep(self.pagination_delay_seconds)

        return jobs

    def _new_jobs(
        self,
        payload: list[object],
        seen_job_ids: set[str],
    ) -> list[dict[str, Any]]:
        new_jobs: list[dict[str, Any]] = []
        for job in payload:
            if not isinstance(job, dict):
                raise ExtractionError("Lever job payload is not an object", raw_payload=job)

            job_id = str(job.get("id") or job.get("hostedUrl") or job.get("text") or "").strip()
            if job_id and job_id in seen_job_ids:
                continue
            if job_id:
                seen_job_ids.add(job_id)
            new_jobs.append(job)
        return new_jobs

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
        return self.COMPANY_BY_TOKEN.get(self.board_token, self.board_token.replace("-", " ").title())

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
