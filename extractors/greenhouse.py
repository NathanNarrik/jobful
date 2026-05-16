from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class GreenhouseExtractor(BaseExtractor):
    provider = "greenhouse"
    api_url_template = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"

    def extract(self) -> list[JobListing]:
        url = self.api_url_template.format(board_token=self.board_token)
        payload = self._get_json(url)

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            self.logger.error("Unexpected Greenhouse payload shape for board %s", self.board_token)
            raise ExtractionError("Unexpected Greenhouse payload schema")

        company_name = self._company_name(payload)
        listings: list[JobListing] = []

        for job in payload["jobs"]:
            if not isinstance(job, dict):
                self.logger.warning("Skipping non-object Greenhouse job on board %s", self.board_token)
                continue

            try:
                listings.append(
                    JobListing(
                        company_name=company_name,
                        job_title=self._required_string(job, "title"),
                        job_url=self._job_url(job),
                        location=self._location(job),
                        raw_description=html_to_text(job.get("content")),
                        ats_provider=self.provider,
                    )
                )
            except (KeyError, TypeError, ValidationError) as exc:
                self.logger.warning(
                    "Skipping malformed Greenhouse job on board %s: %s",
                    self.board_token,
                    exc,
                )

        return listings

    def _company_name(self, payload: dict[str, Any]) -> str:
        return str(payload.get("name") or self.board_token)

    def _job_url(self, job: dict[str, Any]) -> str:
        absolute_url = job.get("absolute_url")
        if isinstance(absolute_url, str) and absolute_url:
            return absolute_url

        job_id = job.get("id")
        if job_id is None:
            raise KeyError("id")

        return f"https://boards.greenhouse.io/{self.board_token}/jobs/{job_id}"

    def _location(self, job: dict[str, Any]) -> str | list[str]:
        location = job.get("location")
        if isinstance(location, dict) and location.get("name"):
            return str(location["name"])

        offices = job.get("offices")
        office_names = [
            str(office["name"])
            for office in offices or []
            if isinstance(office, dict) and office.get("name")
        ]
        return office_names or "Unspecified"

    def _required_string(self, mapping: dict[str, Any], key: str) -> str:
        value = mapping[key]
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"{key} must be a non-empty string")
        return value
