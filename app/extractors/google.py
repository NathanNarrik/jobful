from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from pydantic import ValidationError

from app.extractors.base import BaseExtractor, ExtractionError
from app.extractors.text import html_to_text
from app.models import JobListing


SIGNIN_RE = re.compile(r"https://www\.google\.com/about/careers/applications/signin\?[^\"'<> ]+")
AF_INIT_DATA_RE = re.compile(
    r"AF_initDataCallback\(\{key: 'ds:\d+'.*?data:(.*?), sideChannel",
    re.DOTALL,
)


class GoogleExtractor(BaseExtractor):
    provider = "google"
    results_url_template = "https://www.google.com/about/careers/applications/jobs/results?page={page}"
    max_pages = 500

    def extract(self) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        for page in range(1, self.max_pages + 1):
            html = self._get_text(self.results_url_template.format(page=page))
            page_jobs = self._extract_jobs_from_html(html)
            new_jobs = [job for job in page_jobs if job["ats_job_id"] not in seen_ids]
            if not new_jobs:
                break

            for job in new_jobs:
                seen_ids.add(job["ats_job_id"])
                try:
                    jobs.append(
                        self._build_listing(
                            company_name="Google",
                            job_title=job["job_title"],
                            job_url=job["job_url"],
                            ats_job_id=job["ats_job_id"],
                            location=job["location"],
                            raw_description=html_to_text(str(job["description_html"] or job["job_title"])),
                            description_html=job["description_html"],
                            employment_type=None,
                            departments=job["departments"],
                            date_posted=job["date_posted"],
                        )
                    )
                except (ValidationError, ValueError) as exc:
                    self.logger.error("Failed mapping Google job", exc_info=True)
                    raise ExtractionError("Malformed Google job payload", raw_payload=job) from exc

        if not jobs:
            raise ExtractionError("No Google jobs discovered from careers results pages")

        self.logger.info("Fetched %s Google jobs", len(jobs), extra={"company": "Google"})
        return jobs

    def _get_text(self, url: str) -> str:
        response = self.session.get(url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.text

    def _extract_jobs_from_html(self, html: str) -> list[dict[str, object]]:
        jobs = self._extract_jobs_from_init_data(html)
        if jobs:
            return jobs

        jobs: list[dict[str, object]] = []
        for raw_url in SIGNIN_RE.findall(html):
            url = unescape(raw_url).replace("\\u003d", "=").replace("\\u0026", "&")
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            job_id = unquote(query.get("jobId", [""])[0]).strip()
            title = unquote(query.get("title", [""])[0]).replace("+", " ").strip()
            location = unquote(query.get("loc", [""])[0]).strip()
            if not job_id or not title:
                continue

            jobs.append(
                {
                    "ats_job_id": job_id,
                    "job_title": title,
                    "job_url": urljoin("https://www.google.com", parsed.path + "?" + parsed.query),
                    "location": [location or "Unspecified"],
                    "description_html": None,
                    "departments": [],
                    "date_posted": None,
                }
            )
        return jobs

    def _extract_jobs_from_init_data(self, html: str) -> list[dict[str, object]]:
        jobs: list[dict[str, object]] = []
        for match in AF_INIT_DATA_RE.finditer(html):
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            for record in self._iter_job_records(payload):
                mapped = self._map_record(record)
                if mapped is not None:
                    jobs.append(mapped)
        return jobs

    def _iter_job_records(self, payload: object) -> list[list[Any]]:
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
            return []
        return [record for record in payload[0] if isinstance(record, list) and len(record) > 14]

    def _map_record(self, record: list[Any]) -> dict[str, object] | None:
        job_id = str(record[0] or "").strip()
        title = str(record[1] or "").strip()
        raw_url = str(record[2] or "").strip()
        if not job_id or not title or not raw_url:
            return None

        parsed = urlparse(raw_url)
        location = self._locations(record[9] if len(record) > 9 else None)
        description_html = "\n\n".join(
            html
            for html in (
                self._html_payload(record[10] if len(record) > 10 else None),
                self._html_payload(record[4] if len(record) > 4 else None),
                self._html_payload(record[3] if len(record) > 3 else None),
            )
            if html
        )
        departments = [str(record[7]).strip()] if len(record) > 7 and record[7] else []

        return {
            "ats_job_id": job_id,
            "job_title": title,
            "job_url": urljoin("https://www.google.com", parsed.path + "?" + parsed.query),
            "location": location,
            "description_html": description_html or None,
            "departments": departments,
            "date_posted": self._timestamp_tuple(record[12] if len(record) > 12 else None),
        }

    def _html_payload(self, value: object) -> str | None:
        if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
            return value[1]
        return None

    def _locations(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return ["Unspecified"]
        locations = []
        for item in value:
            if isinstance(item, list) and item and isinstance(item[0], str) and item[0].strip():
                locations.append(item[0].strip())
        return locations or ["Unspecified"]

    def _timestamp_tuple(self, value: object) -> datetime | None:
        if not isinstance(value, list) or not value:
            return None
        try:
            seconds = int(value[0])
            nanos = int(value[1]) if len(value) > 1 and value[1] is not None else 0
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(seconds + nanos / 1_000_000_000, UTC)
