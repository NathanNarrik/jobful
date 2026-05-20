from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

from pydantic import ValidationError

from app.extractors.base import BaseExtractor, ExtractionError
from app.extractors.text import html_to_text
from app.models import JobListing


SMART_APPLY_RE = re.compile(
    r'<code\s+id=["\']smartApplyData["\'][^>]*>(?P<payload>.*?)</code>',
    re.S,
)


class EightfoldExtractor(BaseExtractor):
    provider = "eightfold"
    page_size = 10
    PCSX_BOARDS = {
        "apply.careers.microsoft.com": ("microsoft.com", "Microsoft"),
        "careers.qualcomm.com": ("qualcomm.com", "Qualcomm"),
        "searchcareers.caci.com": ("caci.com", "CACI International"),
    }

    def extract(self) -> list[JobListing]:
        if not self.source_url:
            raise ExtractionError("Eightfold extraction requires the original source URL")

        payload = self._fetch_positions_payload(self.source_url)
        positions = payload.get("positions")
        if not isinstance(positions, list) or not positions:
            raise ExtractionError("Eightfold page did not include positions", raw_payload=payload)

        listings: list[JobListing] = []
        for position in positions:
            if not isinstance(position, dict):
                raise ExtractionError("Eightfold position payload is not an object", raw_payload=position)
            try:
                listings.append(self._map_position(position, payload))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping Eightfold job on board %s", self.board_token, exc_info=True)
                raise ExtractionError("Malformed Eightfold job payload", raw_payload=position) from exc

        self.logger.info("Fetched %s Eightfold jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _fetch_positions_payload(self, source_url: str) -> dict[str, Any]:
        response = self.session.get(source_url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()

        match = SMART_APPLY_RE.search(response.text)
        if match:
            try:
                payload = json.loads(unescape(match.group("payload")))
            except ValueError as exc:
                raise ExtractionError("Eightfold smartApplyData payload is invalid JSON") from exc

            if not isinstance(payload, dict):
                raise ExtractionError("Unexpected Eightfold smartApplyData schema", raw_payload=payload)
            return payload

        if self._is_pcsx_board(source_url):
            return self._fetch_pcsx_positions(source_url)

        raise ExtractionError("Eightfold page did not include smartApplyData")

    def _fetch_smart_apply_payload(self, source_url: str) -> dict[str, Any]:
        response = self.session.get(source_url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()

        match = SMART_APPLY_RE.search(response.text)
        if not match:
            raise ExtractionError("Eightfold page did not include smartApplyData")

        try:
            payload = json.loads(unescape(match.group("payload")))
        except ValueError as exc:
            raise ExtractionError("Eightfold smartApplyData payload is invalid JSON") from exc

        if not isinstance(payload, dict):
            raise ExtractionError("Unexpected Eightfold smartApplyData schema", raw_payload=payload)
        return payload

    def _is_pcsx_board(self, source_url: str) -> bool:
        return (urlparse(source_url).hostname or "") in self.PCSX_BOARDS

    def _fetch_pcsx_positions(self, source_url: str) -> dict[str, Any]:
        parsed = urlparse(source_url)
        hostname = parsed.hostname or ""
        domain, company_name = self.PCSX_BOARDS[hostname]
        api_url = f"{parsed.scheme}://{parsed.hostname}/api/pcsx/search"
        positions: list[dict[str, Any]] = []
        start = 0
        total: int | None = None

        while total is None or start < total:
            payload = self._get_json(f"{api_url}?domain={domain}&query=&location=&start={start}")
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
                raise ExtractionError("Unexpected Eightfold PCS search payload schema", raw_payload=payload)

            data = payload["data"]
            page_positions = data.get("positions")
            if not isinstance(page_positions, list) or not page_positions:
                break

            if total is None:
                count = data.get("count")
                if isinstance(count, (int, str)) and str(count).isdigit():
                    total = int(count)

            positions.extend(position for position in page_positions if isinstance(position, dict))
            start += len(page_positions)
            if len(page_positions) < self.page_size:
                break

        return {
            "positions": positions,
            "branding": {"companyName": company_name},
        }

    def _map_position(self, position: dict[str, Any], payload: dict[str, Any]) -> JobListing:
        job_id = str(
            position.get("ats_job_id")
            or position.get("atsJobId")
            or position.get("display_job_id")
            or position.get("displayJobId")
            or position["id"]
        ).strip()
        title = str(position.get("posting_name") or position.get("name") or "").strip()
        if not title:
            raise KeyError("name")

        description_html = self._optional_string(position.get("job_description") or position.get("jobDescription"))
        return self._build_listing(
            company_name=self._company_name(payload),
            job_title=title,
            job_url=self._job_url(position),
            ats_job_id=job_id,
            location=self._locations(position),
            raw_description=html_to_text(description_html or title),
            description_html=description_html,
            employment_type=self._optional_string(position.get("work_location_option") or position.get("workLocationOption")),
            departments=self._departments(position),
            date_posted=self._parse_datetime(
                position.get("postedTs")
                or position.get("creationTs")
                or position.get("t_create")
                or position.get("t_update")
            ),
        )

    def _company_name(self, payload: dict[str, Any]) -> str:
        branding = payload.get("branding")
        if isinstance(branding, dict):
            company = self._optional_string(branding.get("companyName"))
            if company:
                return company
        return self.board_token.replace("-", " ").title()

    def _job_url(self, position: dict[str, Any]) -> str:
        for key in ("canonicalPositionUrl", "positionUrl", "url"):
            value = self._optional_string(position.get(key))
            if value:
                return urljoin(self.source_url or "", value)
        return f"{self.source_url.rstrip('/')}/job/{position['id']}"

    def _locations(self, position: dict[str, Any]) -> list[str]:
        locations = self._string_list(position.get("locations"))
        if locations:
            return locations
        return self._string_list(position.get("location")) or ["Unspecified"]

    def _departments(self, position: dict[str, Any]) -> list[str]:
        departments: list[str] = []
        for key in ("department", "business_unit", "businessUnit"):
            departments.extend(self._string_list(position.get(key)))
        return list(dict.fromkeys(departments))

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
