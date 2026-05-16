from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests

from models import JobListing


class ExtractionError(RuntimeError):
    """Raised when an ATS extractor cannot safely return normalized jobs."""


class BaseExtractor(ABC):
    provider: str

    def __init__(
        self,
        board_token: str,
        *,
        timeout_seconds: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        if not board_token:
            raise ValueError("board_token must not be empty")

        self.board_token = board_token
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def extract(self) -> list[JobListing]:
        """Fetch active jobs from the ATS and map them into JobListing models."""

    def _get_json(self, url: str) -> object:
        try:
            response = self.session.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            self.logger.exception("Timed out fetching %s", url)
            raise ExtractionError(f"Timed out fetching {self.provider} board") from exc
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            self.logger.exception("HTTP %s fetching %s", status_code, url)
            raise ExtractionError(f"{self.provider} API returned HTTP {status_code}") from exc
        except requests.RequestException as exc:
            self.logger.exception("Network error fetching %s", url)
            raise ExtractionError(f"Network error fetching {self.provider} board") from exc
        except ValueError as exc:
            self.logger.exception("Invalid JSON from %s", url)
            raise ExtractionError(f"{self.provider} API returned invalid JSON") from exc
