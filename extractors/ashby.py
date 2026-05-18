from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class AshbyExtractor(BaseExtractor):
    provider = "ashby"
    api_url_template = "https://api.ashbyhq.com/posting-api/job-board/{board_token}"
    COMPANY_BY_TOKEN = {
        "browserbase": "Browserbase",
        "cartesia": "Cartesia",
        "cognition": "Cognition",
        "cursor": "Cursor",
        "decagon": "Decagon",
        "elevenlabs": "ElevenLabs",
        "factory": "Factory",
        "harvey": "Harvey",
        "langchain": "LangChain",
        "mercor": "Mercor",
        "mistral": "Mistral AI",
        "modal": "Modal",
        "openai": "OpenAI",
        "perplexity": "Perplexity",
        "poolside": "poolside",
    }

    def extract(self) -> list[JobListing]:
        url = self.api_url_template.format(board_token=self.board_token)
        payload = self._get_json(url)

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            self.logger.error("Unexpected Ashby payload shape for board %s", self.board_token)
            raise ExtractionError("Unexpected Ashby payload schema", raw_payload=payload)

        company_name = self._company_name(payload)
        listings: list[JobListing] = []

        for job in payload["jobs"]:
            if not isinstance(job, dict):
                raise ExtractionError("Ashby job payload is not an object", raw_payload=job)
            if job.get("isListed") is False:
                continue

            try:
                listings.append(self._map_job(company_name, job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error(
                    "Failed mapping Ashby job on board %s",
                    self.board_token,
                    exc_info=True,
                )
                raise ExtractionError("Malformed Ashby job payload", raw_payload=job) from exc

        self.logger.info("Fetched %s Ashby jobs", len(listings), extra={"company": company_name})
        return listings

    def _company_name(self, payload: dict[str, Any]) -> str:
        if self.board_token in self.COMPANY_BY_TOKEN:
            return self.COMPANY_BY_TOKEN[self.board_token]
        for key in ("organizationName", "companyName", "name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return self.board_token.replace("-", " ").title()

    def _map_job(self, company_name: str, job: dict[str, Any]) -> JobListing:
        job_id = self._required_string(job, "id")
        description_html = str(job.get("descriptionHtml") or job.get("description") or "")

        return self._build_listing(
            company_name=company_name,
            job_title=self._required_string(job, "title"),
            job_url=self._job_url(job, job_id),
            ats_job_id=job_id,
            location=self._locations(job),
            raw_description=html_to_text(description_html),
            description_html=description_html or None,
            employment_type=self._optional_string(job.get("employmentType")),
            departments=self._departments(job),
            date_posted=self._parse_datetime(job.get("publishedAt") or job.get("createdAt")),
        )

    def _job_url(self, job: dict[str, Any], job_id: str) -> str:
        for key in ("jobUrl", "applyUrl"):
            value = job.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return f"https://jobs.ashbyhq.com/{self.board_token}/{job_id}"

    def _locations(self, job: dict[str, Any]) -> list[str]:
        for key in ("locationName", "location", "locations"):
            locations = self._string_list(job.get(key))
            if locations:
                return locations
        return ["Unspecified"]

    def _departments(self, job: dict[str, Any]) -> list[str]:
        departments: list[str] = []
        for key in ("department", "team"):
            value = job.get(key)
            if isinstance(value, dict) and value.get("name"):
                departments.append(str(value["name"]).strip())
            else:
                departments.extend(self._string_list(value))
        return departments

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
