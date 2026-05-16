from __future__ import annotations

import hashlib
import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import requests

from models import AtsProvider, JobListing
from proxy import ProxyPool


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class ExtractionError(RuntimeError):
    """Raised when an ATS extractor cannot safely return normalized jobs."""

    def __init__(
        self,
        message: str,
        *,
        raw_payload: Any | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload
        self.status_code = status_code


class InvalidBoardError(ExtractionError):
    """Raised when a source URL points to a missing or retired ATS board."""


class RateLimitedError(ExtractionError):
    """Raised when an ATS keeps returning 429 after retries."""


class ForbiddenError(ExtractionError):
    """Raised when an ATS blocks direct HTTP access and needs a browser fallback."""


class BaseExtractor(ABC):
    provider: AtsProvider
    max_retries = 3

    def __init__(
        self,
        board_token: str,
        *,
        source_url: str | None = None,
        timeout_seconds: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        if not board_token:
            raise ValueError("board_token must not be empty")

        self.board_token = board_token
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.proxy_pool = ProxyPool.from_environment()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def extract(self) -> list[JobListing]:
        """Fetch active jobs from the ATS and map them into JobListing models."""

    def _get_json(self, url: str) -> object:
        return self._request_json("GET", url)

    def _post_json(self, url: str, payload: dict[str, Any]) -> object:
        return self._request_json("POST", url, json_payload=payload)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> object:
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    json=json_payload,
                    headers=self._headers(),
                    proxies=self.proxy_pool.next_requests_proxy(),
                    timeout=self.timeout_seconds,
                )

                if response.status_code == 200 and self._is_html_response(response):
                    raise ForbiddenError(
                        f"{self.provider} API returned HTML instead of JSON",
                        status_code=response.status_code,
                    )
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 404:
                    raise InvalidBoardError(
                        f"{self.provider} board returned HTTP 404",
                        status_code=response.status_code,
                    )
                if response.status_code == 403:
                    self.proxy_pool.mark_current_proxy_banned()
                    raise ForbiddenError(
                        f"{self.provider} board returned HTTP 403",
                        status_code=response.status_code,
                    )
                if response.status_code == 429:
                    self.proxy_pool.mark_current_proxy_banned()
                    last_error = RateLimitedError(
                        f"{self.provider} board returned HTTP 429",
                        status_code=response.status_code,
                    )
                    self._sleep_before_retry(attempt, response)
                    continue
                if 500 <= response.status_code <= 599:
                    last_error = ExtractionError(
                        f"{self.provider} API returned HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                    self._sleep_before_retry(attempt, response)
                    continue

                response.raise_for_status()
                return response.json()
            except (ForbiddenError, InvalidBoardError):
                self.logger.error("Unrecoverable status fetching %s", url, exc_info=True)
                raise
            except requests.Timeout as exc:
                last_error = exc
                self.logger.error("Timed out fetching %s", url, exc_info=True)
                self._sleep_before_retry(attempt)
            except requests.RequestException as exc:
                last_error = exc
                self.logger.error("Network error fetching %s", url, exc_info=True)
                self._sleep_before_retry(attempt)
            except ValueError as exc:
                self.logger.error("Invalid JSON from %s", url, exc_info=True)
                raise ExtractionError(f"{self.provider} API returned invalid JSON") from exc

        if isinstance(last_error, ExtractionError):
            raise last_error
        raise ExtractionError(f"Failed fetching {self.provider} board after retries") from last_error

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": random.choice(USER_AGENTS),
        }

    def _is_html_response(self, response: requests.Response) -> bool:
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" in content_type:
            return True
        return response.text.lstrip().startswith("<")

    def _sleep_before_retry(
        self,
        attempt: int,
        response: requests.Response | None = None,
    ) -> None:
        if attempt >= self.max_retries:
            return

        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after and retry_after.isdigit():
            delay = min(float(retry_after), 30.0)
        else:
            delay = min(2.0**attempt, 30.0)
            delay += random.uniform(0.0, delay * 0.1)
        time.sleep(delay)

    def _content_hash(self, company_name: str, job_title: str, ats_job_id: str) -> str:
        value = f"{job_title}|{company_name}|{ats_job_id}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _extracted_at(self) -> datetime:
        return datetime.now(UTC)

    def _parse_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, (int, float)):
            timestamp = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(timestamp, UTC)
        if isinstance(value, str) and value.strip():
            text = value.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return None

    def _build_listing(
        self,
        *,
        company_name: str,
        job_title: str,
        job_url: str,
        ats_job_id: str,
        location: list[str],
        raw_description: str,
        description_html: str | None = None,
        employment_type: str | None = None,
        departments: list[str] | None = None,
        date_posted: datetime | None = None,
    ) -> JobListing:
        return JobListing(
            company_name=company_name,
            job_title=job_title,
            job_url=job_url,
            ats_provider=self.provider,
            ats_job_id=ats_job_id,
            location=location or ["Unspecified"],
            raw_description=raw_description,
            description_html=description_html,
            employment_type=employment_type,
            departments=departments or [],
            date_posted=date_posted,
            content_hash=self._content_hash(company_name, job_title, ats_job_id),
            extracted_at=self._extracted_at(),
        )

    def _required_string(self, mapping: dict[str, Any], key: str) -> str:
        value = mapping[key]
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"{key} must be a non-empty string")
        return value.strip()

    def _string_list(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []
