from __future__ import annotations

from typing import Any
from urllib.parse import quote

from pydantic import ValidationError

from app.extractors.base import BaseExtractor, ExtractionError
from app.extractors.text import html_to_text
from app.models import JobListing


class WalmartExtractor(BaseExtractor):
    provider = "walmart"
    api_url = "https://careers.walmart.com/api/streaming/careers-ai/api/chat/sync?chatBasedSearchJob"
    page_limit = 10
    max_pages = 50
    graphql_query = """
    query GetJobSearchAssistant($chatRequest: JobChatRequest!) {
      jobSearchAssistant(chatRequest: $chatRequest) {
        tool_messages {
          artifact {
            total_jobs
            job_page_number
            jobs {
              job_id
              city
              title
              jobPostingTitle
              state
              country
              brand
              employmentTypes
              jobPostingStartDate
            }
          }
        }
      }
    }
    """

    def extract(self) -> list[JobListing]:
        jobs = self._fetch_all_jobs()
        listings: list[JobListing] = []
        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError):
                self.logger.warning("Skipping malformed Walmart job", exc_info=True)
                continue

        if not listings:
            raise ExtractionError("No Walmart jobs discovered")

        self.logger.info("Fetched %s Walmart jobs", len(listings), extra={"company": "Walmart"})
        return listings

    def _fetch_all_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        total_jobs: int | None = None

        for page in range(self.max_pages):
            try:
                payload = self._search_page(page)
            except Exception:
                if jobs:
                    self.logger.warning("Stopping Walmart pagination after page %s and keeping partial results", page)
                    break
                raise
            artifact = self._artifact(payload)
            if total_jobs is None and isinstance(artifact.get("total_jobs"), int):
                total_jobs = int(artifact["total_jobs"])

            page_jobs = [job for job in artifact.get("jobs", []) if isinstance(job, dict)]
            if not page_jobs:
                break

            for job in page_jobs:
                job_id = str(job.get("job_id") or "").strip()
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                jobs.append(job)

            if total_jobs is not None and len(jobs) >= total_jobs:
                break

        return jobs

    def _search_page(self, page: int) -> dict[str, Any]:
        chat_request = {
            "messages": [{"role": "user", "content": [{"type": "text", "text": "jobs"}]}],
            "thread_id": f"S-jobful-{page}",
            "channel": "job_search",
            "context": {
                "job_search_context": {
                    "active_tab": "jobs",
                    "job_page": page,
                    "content_page": 0,
                    "future_roles_page": 0,
                    "locale": "en_US",
                    "direct_search": True,
                }
            },
        }
        response = self.session.post(
            self.api_url,
            json={"query": self.graphql_query, "variables": {"chatRequest": chat_request}},
            headers={
                **self._headers(),
                "Content-Type": "application/json",
                "Origin": "https://careers.walmart.com",
                "Referer": self.source_url or "https://careers.walmart.com/results",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ExtractionError("Unexpected Walmart jobs payload schema", raw_payload=payload)
        if payload.get("errors"):
            raise ExtractionError("Walmart jobs API returned errors", raw_payload=payload)
        return payload

    def _artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        assistant = payload.get("data", {}).get("jobSearchAssistant") if isinstance(payload.get("data"), dict) else None
        messages = assistant.get("tool_messages") if isinstance(assistant, dict) else None
        if not isinstance(messages, list) or not messages:
            raise ExtractionError("Walmart jobs payload did not include tool messages", raw_payload=payload)
        artifact = messages[0].get("artifact") if isinstance(messages[0], dict) else None
        if not isinstance(artifact, dict):
            raise ExtractionError("Walmart jobs payload did not include an artifact", raw_payload=payload)
        return artifact

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        title = self._required_string(job, "jobPostingTitle")
        job_id = self._required_string(job, "job_id")
        location = ", ".join(
            part
            for part in (
                self._optional_string(job.get("city")),
                self._optional_string(job.get("state")),
                self._optional_string(job.get("country")),
            )
            if part
        )

        return self._build_listing(
            company_name="Walmart",
            job_title=title,
            job_url=self._job_url(job_id, title),
            ats_job_id=job_id,
            location=[location or "Unspecified"],
            raw_description=html_to_text(" | ".join([title, location, self._optional_string(job.get("brand")) or ""])),
            description_html=None,
            employment_type=", ".join(self._string_list(job.get("employmentTypes"))) or None,
            departments=self._string_list(job.get("brand")),
            date_posted=self._parse_datetime(job.get("jobPostingStartDate")),
        )

    def _job_url(self, job_id: str, title: str) -> str:
        slug = quote("-".join(title.lower().split()), safe="-")
        return f"https://careers.walmart.com/job/{slug}/{job_id}"

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
