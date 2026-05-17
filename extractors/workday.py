from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError, ForbiddenError
from extractors.text import html_to_text
from models import JobListing


@dataclass(frozen=True)
class WorkdayContext:
    hostname: str
    tenant: str
    site: str


class WorkdayExtractor(BaseExtractor):
    provider = "workday"
    page_limit = 20
    detail_fetch_limit = 250
    page_load_timeout_ms = 30_000
    COMPANY_BY_TOKEN = {
        "amd": "AMD",
        "arm": "Arm Holdings",
        "cisco": "Cisco Systems",
        "intuit": "Intuit",
        "paloaltonetworks": "Palo Alto Networks",
        "qualcomm": "Qualcomm",
        "ti": "Texas Instruments",
        "vmware": "VMware",
        "zoom": "Zoom Video Communications",
    }

    def extract(self) -> list[JobListing]:
        if not self.source_url:
            raise ExtractionError("Workday extraction requires the original source URL")

        try:
            jobs = self._fetch_direct_cxs_jobs(self.source_url)
        except ForbiddenError:
            payloads = self._collect_browser_payloads(self.source_url)
            jobs = self._find_jobs(payloads)

        if not jobs:
            raise ExtractionError("No Workday job payloads discovered")

        listings: list[JobListing] = []
        for job in jobs:
            if not isinstance(job, dict):
                raise ExtractionError("Workday job payload is not an object", raw_payload=job)

            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error(
                    "Failed mapping Workday job on board %s",
                    self.board_token,
                    exc_info=True,
                )
                raise ExtractionError("Malformed Workday job payload", raw_payload=job) from exc

        self.logger.info("Fetched %s Workday jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _fetch_direct_cxs_jobs(self, source_url: str) -> list[dict[str, Any]]:
        context = self._context_from_url(source_url)
        jobs_url = f"https://{context.hostname}/wday/cxs/{context.tenant}/{context.site}/jobs"
        offset = 0
        total: int | None = None
        jobs: list[dict[str, Any]] = []

        while total is None or offset < total:
            payload = self._post_json(
                jobs_url,
                {
                    "appliedFacets": {},
                    "limit": self.page_limit,
                    "offset": offset,
                    "searchText": "",
                },
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("jobPostings"), list):
                raise ExtractionError("Unexpected Workday jobs payload schema", raw_payload=payload)

            total_value = payload.get("total")
            if total is None and isinstance(total_value, (int, str)) and str(total_value).isdigit():
                total = int(total_value)
            postings = payload["jobPostings"]
            if not postings:
                break
            should_fetch_details = total is None or total <= self.detail_fetch_limit

            for posting in postings:
                if not isinstance(posting, dict):
                    raise ExtractionError("Workday posting payload is not an object", raw_payload=posting)
                if should_fetch_details:
                    jobs.append(self._fetch_direct_cxs_detail(context, posting))
                else:
                    jobs.append(posting)

            offset += len(postings)
            if total is None and len(postings) < self.page_limit:
                break

        return jobs

    def _fetch_direct_cxs_detail(
        self,
        context: WorkdayContext,
        posting: dict[str, Any],
    ) -> dict[str, Any]:
        external_path = posting.get("externalPath")
        if not isinstance(external_path, str) or not external_path.strip():
            return posting

        detail_url = f"https://{context.hostname}/wday/cxs/{context.tenant}/{context.site}{external_path}"
        payload = self._get_json(detail_url)
        if isinstance(payload, dict) and isinstance(payload.get("jobPostingInfo"), dict):
            merged = {**posting, **payload["jobPostingInfo"]}
            merged.setdefault("externalPath", external_path)
            return merged
        return posting

    def _context_from_url(self, source_url: str) -> WorkdayContext:
        parsed = urlparse(source_url)
        hostname = parsed.hostname or ""
        tenant = hostname.split(".", maxsplit=1)[0]
        path_parts = [part for part in parsed.path.split("/") if part]
        site = path_parts[0] if path_parts and path_parts[0].lower() not in {"en-us", "en"} else ""
        if not site and len(path_parts) > 1:
            site = path_parts[1]
        if not hostname or not tenant or not site:
            raise ExtractionError("Could not determine Workday tenant/site from URL")
        return WorkdayContext(hostname=hostname, tenant=tenant, site=site)

    def _collect_browser_payloads(self, source_url: str) -> list[object]:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ExtractionError(
                "Workday extraction requires optional dependency playwright. "
                "Install it and run `python -m playwright install chromium`."
            ) from exc

        payloads: list[object] = []

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(user_agent=self._headers()["User-Agent"])
                self._apply_stealth(page)

                def capture_response(response: Any) -> None:
                    url = response.url.lower()
                    if not any(marker in url for marker in ("jobs", "jobpostings", "postings")):
                        return
                    try:
                        payloads.append(response.json())
                    except Exception:
                        return

                page.on("response", capture_response)
                page.goto(source_url, wait_until="networkidle", timeout=self.page_load_timeout_ms)
                browser.close()
        except PlaywrightError as exc:
            raise ExtractionError("Workday browser extraction failed") from exc

        return payloads

    def _apply_stealth(self, page: Any) -> None:
        try:
            from playwright_stealth import stealth_sync
        except ImportError:
            return
        stealth_sync(page)

    def _find_jobs(self, payloads: list[object]) -> list[dict[str, Any]]:
        for payload in payloads:
            jobs = self._extract_jobs_from_payload(payload)
            if jobs:
                return jobs
        return []

    def _extract_jobs_from_payload(self, payload: object) -> list[dict[str, Any]]:
        if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
            return payload

        if not isinstance(payload, dict):
            return []

        for key in ("jobPostings", "jobs", "postings", "data"):
            value = payload.get(key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
            if isinstance(value, dict):
                nested = self._extract_jobs_from_payload(value)
                if nested:
                    return nested

        return []

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        job_id = self._job_id(job)
        title = self._job_title(job)
        job_url = self._job_url(job, job_id)
        description_html = self._description_html(job)

        return self._build_listing(
            company_name=self._company_name(),
            job_title=title,
            job_url=job_url,
            ats_job_id=job_id,
            location=self._locations(job),
            raw_description=html_to_text(description_html or job.get("description") or title),
            description_html=description_html,
            employment_type=self._optional_string(job.get("timeType") or job.get("workerSubType")),
            departments=self._string_list(job.get("jobFamily") or job.get("jobFamilyGroup")),
            date_posted=self._date_posted(job),
        )

    def _company_name(self) -> str:
        return self.COMPANY_BY_TOKEN.get(self.board_token, self.board_token.replace("-", " ").title())

    def _date_posted(self, job: dict[str, Any]) -> datetime | None:
        for key in ("startDate", "postedOn", "postedDate", "datePosted"):
            value = job.get(key)
            parsed = self._parse_datetime(value)
            if parsed is not None:
                return parsed
            parsed = self._parse_relative_posted_on(value)
            if parsed is not None:
                return parsed
        return None

    def _parse_relative_posted_on(self, value: object) -> datetime | None:
        if not isinstance(value, str):
            return None

        text = value.strip().lower()
        now = datetime.now(UTC)
        if text in {"posted today", "today"}:
            return now
        if text in {"posted yesterday", "yesterday"}:
            return now - timedelta(days=1)

        match = re.fullmatch(r"posted\s+(\d+)\+?\s+days?\s+ago", text)
        if match:
            return now - timedelta(days=int(match.group(1)))
        return None

    def _job_id(self, job: dict[str, Any]) -> str:
        for key in ("jobReqId", "requisitionId", "id", "bulletFields", "externalPath"):
            value = job.get(key)
            if isinstance(value, list) and value:
                return str(value[0]).strip()
            if value:
                return str(value).strip().split("/")[-1]
        raise KeyError("id")

    def _job_title(self, job: dict[str, Any]) -> str:
        for key in ("title", "jobTitle", "name"):
            value = job.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise KeyError("title")

    def _job_url(self, job: dict[str, Any], job_id: str) -> str:
        for key in ("externalPath", "jobPostingUrl", "applyUrl"):
            value = job.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                if key == "externalPath" and text.startswith("/") and self.source_url:
                    context = self._context_from_url(self.source_url)
                    return f"https://{context.hostname}/{context.site}{text}"
                return urljoin(self.source_url or "", text)
        return urljoin(self.source_url or "", job_id)

    def _locations(self, job: dict[str, Any]) -> list[str]:
        for key in ("locationsText", "location", "locations", "primaryLocation"):
            locations = self._string_list(job.get(key))
            if locations:
                return locations
        return ["Unspecified"]

    def _description_html(self, job: dict[str, Any]) -> str | None:
        for key in ("jobDescription", "descriptionHtml", "description"):
            value = job.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
