from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class VerizonExtractor(BaseExtractor):
    provider = "verizon"
    api_url = "https://mycareer.verizon.com/api/jobs/search/"
    page_limit = 100
    max_pages = 20

    def extract(self) -> list[JobListing]:
        jobs = self._fetch_all_jobs()
        listings: list[JobListing] = []
        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError):
                self.logger.warning("Skipping malformed Verizon job", exc_info=True)
                continue

        if not listings:
            raise ExtractionError("No Verizon jobs discovered")

        self.logger.info("Fetched %s Verizon jobs", len(listings), extra={"company": "Verizon Communications"})
        return listings

    def _fetch_all_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        total_pages = 1

        for page in range(1, self.max_pages + 1):
            payload = self._get_json(f"{self.api_url}?page={page}&pagesize={self.page_limit}")
            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                raise ExtractionError("Unexpected Verizon jobs payload schema", raw_payload=payload)

            if isinstance(payload.get("totalPages"), int):
                total_pages = int(payload["totalPages"])

            page_jobs = [job for job in payload["jobs"] if isinstance(job, dict)]
            if not page_jobs:
                break

            for job in page_jobs:
                job_id = str(job.get("Id") or "").strip()
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                jobs.append(job)

            if page >= total_pages:
                break

        return jobs

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        title = self._required_string(job, "Title")
        locations = self._locations(job)
        departments = self._string_list(job.get("Teams"))

        return self._build_listing(
            company_name="Verizon Communications",
            job_title=title,
            job_url=self._job_url(job),
            ats_job_id=self._required_string(job, "Id"),
            location=locations,
            raw_description=html_to_text(" | ".join([title, ", ".join(locations), ", ".join(departments)])),
            description_html=None,
            employment_type=None,
            departments=departments,
            date_posted=None,
        )

    def _job_url(self, job: dict[str, Any]) -> str:
        urls = job.get("Urls")
        if isinstance(urls, list):
            for item in urls:
                if isinstance(item, dict) and item.get("IsDefault") and isinstance(item.get("Url"), str):
                    return urljoin("https://mycareer.verizon.com", item["Url"])
            for item in urls:
                if isinstance(item, dict) and isinstance(item.get("Url"), str):
                    return urljoin("https://mycareer.verizon.com", item["Url"])
        return urljoin("https://mycareer.verizon.com/jobs/", self._required_string(job, "Id"))

    def _locations(self, job: dict[str, Any]) -> list[str]:
        locations = job.get("Locations")
        values: list[str] = []
        if isinstance(locations, list):
            for location in locations:
                if not isinstance(location, dict):
                    continue
                text = self._location_text(location)
                if text:
                    values.append(text)
        return list(dict.fromkeys(values)) or ["Unspecified"]

    def _location_text(self, location: dict[str, Any]) -> str | None:
        for key in ("Identifier", "City", "Country"):
            value = location.get(key)
            if isinstance(value, str) and value.strip():
                if key == "City":
                    region = location.get("Region")
                    country = location.get("Country")
                    parts = [value.strip()]
                    if isinstance(region, str) and region.strip() and region.strip() != value.strip():
                        parts.append(region.strip())
                    if isinstance(country, str) and country.strip() and country.strip() not in parts:
                        parts.append(country.strip())
                    return ", ".join(parts)
                return value.strip()
        return None
