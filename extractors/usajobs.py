from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import requests
from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError, InvalidBoardError
from models import JobListing


class USAJobsExtractor(BaseExtractor):
    provider = "usajobs"
    search_endpoint = "https://www.usajobs.gov/Search/ExecuteSearch"
    page_size = 25
    max_pages = 100

    COMPANY_BY_TOKEN = {
        "nasa": "NASA",
    }
    DEPARTMENT_BY_TOKEN = {
        "nasa": "NN",
    }
    OPEN_DATE_RE = re.compile(r"\bOpen\s+(\d{1,2}/\d{1,2}/\d{4})\b", re.IGNORECASE)

    def extract(self) -> list[JobListing]:
        department = self.DEPARTMENT_BY_TOKEN.get(self.board_token)
        if department is None:
            raise InvalidBoardError(f"Unsupported USAJOBS department token: {self.board_token}")

        jobs = self._fetch_all_jobs(department)
        listings: list[JobListing] = []

        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping USAJOBS job", exc_info=True)
                raise ExtractionError("Malformed USAJOBS job payload", raw_payload=job) from exc

        if not listings:
            raise ExtractionError("No USAJOBS jobs discovered")

        self.logger.info("Fetched %s USAJOBS jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _fetch_all_jobs(self, department: str) -> list[dict[str, Any]]:
        seed_url = self.source_url or f"https://www.usajobs.gov/Search/Results?d={department}"
        headers = {
            **self._headers(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.session.get(seed_url, headers=headers, timeout=self.timeout_seconds)

        jobs: list[dict[str, Any]] = []
        for page in range(1, self.max_pages + 1):
            payload = self._post_search(department, page, seed_url)
            page_jobs = payload.get("Jobs")
            if not isinstance(page_jobs, list):
                raise ExtractionError("Unexpected USAJOBS search payload schema", raw_payload=payload)

            current_jobs = [job for job in page_jobs if isinstance(job, dict)]
            if not current_jobs:
                break
            jobs.extend(current_jobs)

            page_count = self._page_count(payload)
            if page >= page_count:
                break

        return jobs

    def _post_search(self, department: str, page: int, referer: str) -> dict[str, Any]:
        payload = {
            "Department": [department],
            "Page": str(page),
            "ResultsPerPage": self.page_size,
        }
        headers = {
            **self._headers(),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=utf-8",
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            response = self.session.post(
                self.search_endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
            if response.status_code == 404:
                raise InvalidBoardError("USAJOBS search returned HTTP 404", status_code=response.status_code)
            if response.status_code >= 400:
                raise ExtractionError(
                    f"USAJOBS search returned HTTP {response.status_code}",
                    status_code=response.status_code,
                    raw_payload=response.text[:1000],
                )
            result = response.json()
        except requests.RequestException as exc:
            raise ExtractionError("Network error fetching USAJOBS search") from exc
        except ValueError as exc:
            raise ExtractionError("USAJOBS search returned invalid JSON") from exc

        if not isinstance(result, dict):
            raise ExtractionError("Unexpected USAJOBS search payload schema", raw_payload=result)
        return result

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        title = self._required_string(job, "Title")
        job_id = str(job.get("DocumentID") or job.get("PositionID") or "").strip()
        if not job_id:
            raise TypeError("USAJOBS job id must be present")

        agency = self._optional_string(job.get("Agency"))
        department = self._optional_string(job.get("Department"))
        category_names = self._job_category_names(job)
        date_display = self._optional_string(job.get("DateDisplay"))
        raw_description = " | ".join(
            part
            for part in [
                title,
                agency,
                department,
                ", ".join(category_names),
                self._optional_string(job.get("WorkType")),
                self._optional_string(job.get("WorkSchedule")),
                date_display,
            ]
            if part
        )

        return self._build_listing(
            company_name=self.COMPANY_BY_TOKEN.get(self.board_token, self.board_token.upper()),
            job_title=title,
            job_url=self._job_url(job, job_id),
            ats_job_id=job_id,
            location=[self._location(job)],
            raw_description=raw_description,
            employment_type=self._optional_string(job.get("WorkType") or job.get("WorkSchedule")),
            departments=[value for value in [agency, department, *category_names] if value],
            date_posted=self._parse_open_date(date_display),
        )

    def _page_count(self, payload: dict[str, Any]) -> int:
        pager = payload.get("Pager")
        if isinstance(pager, dict):
            value = pager.get("NumberOfPages")
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return 1

    def _job_url(self, job: dict[str, Any], job_id: str) -> str:
        for key in ("PositionURI", "ApplyURI", "DetailsURI"):
            value = job.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().replace("https://www.usajobs.gov:443/", "https://www.usajobs.gov/")
        return f"https://www.usajobs.gov/job/{job_id}"

    def _location(self, job: dict[str, Any]) -> str:
        for key in ("Location", "LocationName", "Locations"):
            value = job.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "Unspecified"

    def _job_category_names(self, job: dict[str, Any]) -> list[str]:
        categories = job.get("JobCategoryCode")
        if not isinstance(categories, list):
            return []

        values: list[str] = []
        for category in categories:
            if not isinstance(category, dict):
                continue
            value = category.get("Name") or category.get("Code") or category.get("Display")
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
        return values

    def _parse_open_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        match = self.OPEN_DATE_RE.search(value)
        if not match:
            return None
        return datetime.strptime(match.group(1), "%m/%d/%Y").replace(tzinfo=UTC)

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
