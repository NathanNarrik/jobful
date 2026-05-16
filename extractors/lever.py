from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class LeverExtractor(BaseExtractor):
    provider = "lever"
    api_url_template = "https://api.lever.co/v0/postings/{board_token}?mode=json"

    def extract(self) -> list[JobListing]:
        url = self.api_url_template.format(board_token=self.board_token)
        payload = self._get_json(url)

        if not isinstance(payload, list):
            self.logger.error("Unexpected Lever payload shape for board %s", self.board_token)
            raise ExtractionError("Unexpected Lever payload schema")

        listings: list[JobListing] = []

        for job in payload:
            if not isinstance(job, dict):
                self.logger.warning("Skipping non-object Lever job on board %s", self.board_token)
                continue

            try:
                listings.append(
                    JobListing(
                        company_name=self._company_name(),
                        job_title=self._required_string(job, "text"),
                        job_url=self._required_string(job, "hostedUrl"),
                        location=self._location(job),
                        raw_description=self._raw_description(job),
                        ats_provider=self.provider,
                    )
                )
            except (KeyError, TypeError, ValidationError) as exc:
                self.logger.warning(
                    "Skipping malformed Lever job on board %s: %s",
                    self.board_token,
                    exc,
                )

        return listings

    def _company_name(self) -> str:
        return self.board_token.replace("-", " ").title()

    def _location(self, job: dict[str, Any]) -> str:
        categories = job.get("categories")
        if isinstance(categories, dict) and categories.get("location"):
            return str(categories["location"])
        return "Unspecified"

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

    def _required_string(self, mapping: dict[str, Any], key: str) -> str:
        value = mapping[key]
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"{key} must be a non-empty string")
        return value
