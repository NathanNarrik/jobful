from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


ORACLE_BASE_RE = re.compile(r"https://[^\"']+/hcmRestApi/CandidateExperience/siteFavicon")
SITE_NUMBER_RE = re.compile(r"siteNumber=([^&\"']+)")


class OracleExtractor(BaseExtractor):
    provider = "oracle"
    page_limit = 100
    max_pages = 100
    COMPANY_BY_HOST = {
        "careers.ti.com": "Texas Instruments",
        "careers.honeywell.com": "Honeywell",
        "eeho.fa.us2.oraclecloud.com": "Oracle",
        "jpmc.fa.oraclecloud.com": "JPMorgan Chase",
        "hdpc.fa.us2.oraclecloud.com": "Goldman Sachs",
    }

    def extract(self) -> list[JobListing]:
        if not self.source_url:
            raise ExtractionError("Oracle extraction requires the original source URL")

        oracle_base_url, site_number = self._discover_context(self.source_url)
        jobs = self._fetch_all_jobs(oracle_base_url, site_number)
        listings: list[JobListing] = []

        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping Oracle job on board %s", self.board_token, exc_info=True)
                raise ExtractionError("Malformed Oracle job payload", raw_payload=job) from exc

        self.logger.info("Fetched %s Oracle jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _discover_context(self, source_url: str) -> tuple[str, str]:
        inferred = self._infer_context_from_url(source_url)
        if inferred is not None:
            return inferred

        response = self.session.get(source_url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()
        html = response.text

        base_match = ORACLE_BASE_RE.search(html)
        site_match = SITE_NUMBER_RE.search(html)
        if not base_match or not site_match:
            raise ExtractionError("Could not discover Oracle Recruiting context from page HTML")

        oracle_base_url = base_match.group(0).split("/hcmRestApi/", maxsplit=1)[0]
        return oracle_base_url, site_match.group(1)

    def _infer_context_from_url(self, source_url: str) -> tuple[str, str] | None:
        parsed = urlparse(source_url)
        hostname = parsed.hostname or ""
        path_parts = [part for part in parsed.path.split("/") if part]
        if not hostname.endswith(".oraclecloud.com") or "sites" not in path_parts:
            return None

        site_index = path_parts.index("sites") + 1
        if site_index >= len(path_parts):
            return None
        return f"{parsed.scheme}://{hostname}", path_parts[site_index]

    def _fetch_all_jobs(self, oracle_base_url: str, site_number: str) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        offset = 0
        total: int | None = None

        while total is None or offset < total:
            url = (
                f"{oracle_base_url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                "?onlyData=true"
                "&expand=requisitionList.workLocation,requisitionList.otherWorkLocations,"
                "requisitionList.secondaryLocations,flexFieldsFacet.values,"
                "requisitionList.requisitionFlexFields"
                f"&finder=findReqs;siteNumber={site_number},limit={self.page_limit},offset={offset}"
            )
            payload = self._get_json(url)
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise ExtractionError("Unexpected Oracle jobs payload schema", raw_payload=payload)

            if not payload["items"]:
                break
            search_result = payload["items"][0]
            if not isinstance(search_result, dict):
                raise ExtractionError("Unexpected Oracle search result schema", raw_payload=payload)

            if total is None:
                total_value = search_result.get("TotalJobsCount")
                if isinstance(total_value, (int, str)) and str(total_value).isdigit():
                    total = int(total_value)

            page_jobs = search_result.get("requisitionList")
            if not isinstance(page_jobs, list) or not page_jobs:
                break

            jobs.extend(job for job in page_jobs if isinstance(job, dict) and self._is_open(job))
            offset += len(page_jobs)
            if len(page_jobs) < self.page_limit:
                break
            if offset >= self.page_limit * self.max_pages:
                self.logger.warning(
                    "Stopping Oracle pagination for board %s after %s pages",
                    self.board_token,
                    self.max_pages,
                )
                break

        return jobs

    def _is_open(self, job: dict[str, Any]) -> bool:
        posting_end = self._parse_datetime(job.get("PostingEndDate"))
        if posting_end is None:
            return True
        return posting_end >= datetime.now(UTC)

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        job_id = str(job["Id"]).strip()
        description_html = "\n\n".join(
            str(value)
            for value in (
                job.get("ShortDescriptionStr"),
                job.get("ExternalResponsibilitiesStr"),
                job.get("ExternalQualificationsStr"),
            )
            if value
        )

        return self._build_listing(
            company_name=self._company_name(),
            job_title=self._required_string(job, "Title"),
            job_url=self._job_url(job_id),
            ats_job_id=job_id,
            location=self._locations(job),
            raw_description=html_to_text(description_html),
            description_html=description_html or None,
            employment_type=self._optional_string(job.get("JobSchedule") or job.get("WorkerType")),
            departments=self._departments(job),
            date_posted=self._parse_datetime(job.get("PostedDate")),
        )

    def _company_name(self) -> str:
        if self.source_url:
            hostname = urlparse(self.source_url).hostname or ""
            if hostname in self.COMPANY_BY_HOST:
                return self.COMPANY_BY_HOST[hostname]
        return self.board_token.replace("-", " ").title()

    def _job_url(self, job_id: str) -> str:
        return urljoin(self.source_url or "", f"job/{job_id}")

    def _locations(self, job: dict[str, Any]) -> list[str]:
        locations = self._string_list(job.get("PrimaryLocation"))
        for key in ("workLocation", "secondaryLocations", "otherWorkLocations"):
            value = job.get(key)
            if isinstance(value, list):
                for location in value:
                    if isinstance(location, dict):
                        locations.extend(self._string_list(location.get("LocationName")))
                    else:
                        locations.extend(self._string_list(location))
        return list(dict.fromkeys(locations)) or ["Unspecified"]

    def _departments(self, job: dict[str, Any]) -> list[str]:
        departments: list[str] = []
        for key in ("JobFamily", "JobFunction", "Department", "BusinessUnit", "Organization"):
            departments.extend(self._string_list(job.get(key)))
        return list(dict.fromkeys(departments))

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
