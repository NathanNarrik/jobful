from __future__ import annotations

import json
import math
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


HYDRATION_RE = re.compile(r'JSON\.parse\("((?:\\.|[^"\\])*)"\)', re.S)


class AppleExtractor(BaseExtractor):
    provider = "apple"
    default_search_url = "https://jobs.apple.com/en-us/search?sort=relevance"
    max_pages = 400

    def extract(self) -> list[JobListing]:
        first_page_url = self.source_url or self.default_search_url
        first_payload = self._fetch_search_payload(first_page_url)
        first_jobs = self._search_results(first_payload)
        total_records = self._total_records(first_payload)
        page_size = max(len(first_jobs), 1)
        page_count = min(self.max_pages, max(1, math.ceil(total_records / page_size)))

        raw_jobs = list(first_jobs)
        seen_ids = {self._job_id(job) for job in first_jobs if self._job_id(job)}

        for page in range(2, page_count + 1):
            payload = self._fetch_search_payload(self._page_url(first_page_url, page))
            page_jobs = self._search_results(payload)
            if not page_jobs:
                break

            new_jobs: list[dict[str, Any]] = []
            for job in page_jobs:
                job_id = self._job_id(job)
                if job_id and job_id in seen_ids:
                    continue
                if job_id:
                    seen_ids.add(job_id)
                new_jobs.append(job)

            raw_jobs.extend(new_jobs)

        listings: list[JobListing] = []
        for job in raw_jobs:
            if job.get("postExternal") is False:
                continue
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping Apple job", exc_info=True)
                raise ExtractionError("Malformed Apple job payload", raw_payload=job) from exc

        if not listings:
            raise ExtractionError("No Apple jobs discovered from careers search pages")

        self.logger.info("Fetched %s Apple jobs", len(listings), extra={"company": "Apple"})
        return listings

    def _fetch_search_payload(self, url: str) -> dict[str, Any]:
        response = self.session.get(url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = self._decode_hydration_payload(response.text)
        search_payload = self._find_search_payload(payload)
        if search_payload is None:
            raise ExtractionError("Apple page did not include search results payload", raw_payload=url)
        return search_payload

    def _decode_hydration_payload(self, html: str) -> object:
        for match in HYDRATION_RE.finditer(html):
            try:
                decoded = json.loads(f'"{match.group(1)}"')
                return json.loads(decoded)
            except ValueError:
                continue
        raise ExtractionError("Apple page did not include router hydration JSON")

    def _find_search_payload(self, value: object) -> dict[str, Any] | None:
        if isinstance(value, dict):
            if isinstance(value.get("searchResults"), list):
                return value
            for nested in value.values():
                found = self._find_search_payload(nested)
                if found is not None:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = self._find_search_payload(nested)
                if found is not None:
                    return found
        return None

    def _search_results(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        jobs = payload.get("searchResults")
        if not isinstance(jobs, list):
            raise ExtractionError("Unexpected Apple search payload schema", raw_payload=payload)
        return [job for job in jobs if isinstance(job, dict)]

    def _total_records(self, payload: dict[str, Any]) -> int:
        value = payload.get("totalRecords")
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return len(self._search_results(payload))

    def _page_url(self, base_url: str, page: int) -> str:
        parsed = urlparse(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["page"] = str(page)
        return urlunparse(parsed._replace(query=urlencode(query)))

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        job_id = self._job_id(job)
        title = self._required_string(job, "postingTitle")
        description = str(job.get("jobSummary") or title)
        team = job.get("team") if isinstance(job.get("team"), dict) else {}

        return self._build_listing(
            company_name="Apple",
            job_title=title,
            job_url=self._job_url(job),
            ats_job_id=job_id,
            location=self._locations(job),
            raw_description=html_to_text(description),
            description_html=description,
            employment_type=self._optional_string(job.get("type")),
            departments=self._string_list(team.get("teamName") if isinstance(team, dict) else None),
            date_posted=self._parse_datetime(job.get("postDateInGMT")),
        )

    def _job_id(self, job: dict[str, Any]) -> str:
        return str(job.get("id") or job.get("reqId") or job.get("positionId") or "").strip()

    def _job_url(self, job: dict[str, Any]) -> str:
        job_id = self._job_id(job)
        detail_id = self._detail_id(job)
        slug = str(job.get("transformedPostingTitle") or "").strip()
        team = job.get("team") if isinstance(job.get("team"), dict) else {}
        team_code = str(team.get("teamCode") or "").strip() if isinstance(team, dict) else ""
        path = f"/en-us/details/{detail_id}/{slug}" if slug else f"/en-us/details/{detail_id}"
        url = urljoin("https://jobs.apple.com", path)
        if team_code:
            url = f"{url}?{urlencode({'team': team_code})}"
        return url

    def _detail_id(self, job: dict[str, Any]) -> str:
        job_id = self._job_id(job)
        if job_id.startswith(("PIPE-", "REQ-")):
            position_id = str(job.get("positionId") or "").strip()
            if position_id:
                return position_id
        return job_id

    def _locations(self, job: dict[str, Any]) -> list[str]:
        values: list[str] = []
        locations = job.get("locations")
        if isinstance(locations, list):
            for location in locations:
                if not isinstance(location, dict):
                    continue
                name = str(location.get("name") or "").strip()
                country = str(location.get("countryName") or "").strip()
                if name and country:
                    values.append(f"{name}, {country}")
                elif name or country:
                    values.append(name or country)
        return values or ["Unspecified"]

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
