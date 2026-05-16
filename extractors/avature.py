from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from datetime import UTC
from typing import Any
from urllib.parse import urljoin, urlparse

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class AvatureRssExtractor(BaseExtractor):
    provider = "avature"

    COMPANY_BY_HOST = {
        "careers.twosigma.com": "Two Sigma",
    }

    def extract(self) -> list[JobListing]:
        if not self.source_url:
            raise ExtractionError("Avature RSS extraction requires the original source URL")

        jobs = self._fetch_feed_jobs()
        listings: list[JobListing] = []
        for job in jobs:
            try:
                listings.append(self._map_job(job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error("Failed mapping Avature RSS job on board %s", self.board_token, exc_info=True)
                raise ExtractionError("Malformed Avature RSS job payload", raw_payload=job) from exc

        self.logger.info("Fetched %s Avature RSS jobs", len(listings), extra={"company": self.board_token})
        return listings

    def _fetch_feed_jobs(self) -> list[dict[str, Any]]:
        feed_url = self._feed_url()
        response = self.session.get(feed_url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        jobs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for item in root.findall("./channel/item"):
            job_url = self._item_text(item, "link") or self._item_text(item, "guid")
            title = self._item_text(item, "title")
            if not job_url or not title:
                continue
            job_id = job_url.rstrip("/").split("/")[-1]
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            jobs.append(
                {
                    "id": job_id,
                    "title": title,
                    "url": job_url,
                    "location": self._item_text(item, "description") or "Unspecified",
                    "date_posted": self._item_text(item, "pubDate"),
                }
            )

        if not jobs:
            raise ExtractionError("No Avature RSS jobs discovered")
        return jobs

    def _feed_url(self) -> str:
        assert self.source_url is not None
        if "/feed" in self.source_url:
            return self.source_url
        return urljoin(self.source_url.rstrip("/") + "/", "feed/?jobRecordsPerPage=100&jobOffset=0")

    def _item_text(self, item: ET.Element, tag: str) -> str | None:
        node = item.find(tag)
        if node is None or node.text is None:
            return None
        text = node.text.strip()
        return text or None

    def _map_job(self, job: dict[str, Any]) -> JobListing:
        title = self._required_string(job, "title")
        return self._build_listing(
            company_name=self._company_name(),
            job_title=title,
            job_url=self._required_string(job, "url"),
            ats_job_id=self._required_string(job, "id"),
            location=self._string_list(job.get("location")) or ["Unspecified"],
            raw_description=html_to_text(" | ".join([title, str(job.get("location") or "")])),
            description_html=None,
            employment_type=None,
            departments=[],
            date_posted=self._parse_pubdate(job.get("date_posted")),
        )

    def _parse_pubdate(self, value: object):
        if not isinstance(value, str) or not value.strip():
            return None
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def _company_name(self) -> str:
        if self.source_url:
            hostname = urlparse(self.source_url).hostname or ""
            if hostname in self.COMPANY_BY_HOST:
                return self.COMPANY_BY_HOST[hostname]
        return self.board_token.replace("-", " ").title()
