from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Type
from urllib.parse import parse_qs, urlparse

from extractors.base import BaseExtractor
from extractors.greenhouse import GreenhouseExtractor
from extractors.lever import LeverExtractor
from models import JobListing


class UnsupportedAtsError(ValueError):
    """Raised when a career URL cannot be routed to a supported ATS provider."""


@dataclass(frozen=True)
class AtsRoute:
    provider: str
    board_token: str
    extractor_class: Type[BaseExtractor]


class AtsRouter:
    def __init__(self) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def route(self, career_url: str) -> AtsRoute:
        parsed = urlparse(career_url)
        hostname = (parsed.hostname or "").lower()
        path_parts = [part for part in parsed.path.split("/") if part]

        if self._is_greenhouse(hostname):
            token = self._greenhouse_token(hostname, path_parts)
            return AtsRoute("greenhouse", token, GreenhouseExtractor)

        if self._is_lever(hostname):
            token = self._lever_token(hostname, path_parts, parsed.query)
            return AtsRoute("lever", token, LeverExtractor)

        raise UnsupportedAtsError(f"Unsupported or unrecognized ATS URL: {career_url}")

    def extract(self, career_url: str) -> list[JobListing]:
        route = self.route(career_url)
        self.logger.info("Routing %s to %s board %s", career_url, route.provider, route.board_token)
        return route.extractor_class(route.board_token).extract()

    def _is_greenhouse(self, hostname: str) -> bool:
        return hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io"} or hostname.endswith(
            ".greenhouse.io"
        )

    def _greenhouse_token(self, hostname: str, path_parts: list[str]) -> str:
        if hostname == "boards-api.greenhouse.io":
            board_index = self._index_after(path_parts, "boards")
            if board_index is not None:
                return path_parts[board_index]

        if path_parts:
            return path_parts[0]

        subdomain = hostname.removesuffix(".greenhouse.io")
        if subdomain and subdomain not in {"boards", "boards-api", "job-boards"}:
            return subdomain

        raise UnsupportedAtsError("Could not determine Greenhouse board token")

    def _is_lever(self, hostname: str) -> bool:
        return hostname in {"jobs.lever.co", "api.lever.co"} or hostname.endswith(".lever.co")

    def _lever_token(self, hostname: str, path_parts: list[str], query: str) -> str:
        if hostname == "api.lever.co":
            postings_index = self._index_after(path_parts, "postings")
            if postings_index is not None:
                return path_parts[postings_index]

        if path_parts:
            return path_parts[0]

        query_values = parse_qs(query)
        for key in ("company", "team", "token"):
            value = query_values.get(key, [None])[0]
            if value:
                return value

        subdomain = hostname.removesuffix(".lever.co")
        if subdomain and subdomain not in {"jobs", "api"}:
            return subdomain

        raise UnsupportedAtsError("Could not determine Lever board token")

    def _index_after(self, path_parts: list[str], marker: str) -> int | None:
        try:
            marker_index = path_parts.index(marker)
        except ValueError:
            return None

        target_index = marker_index + 1
        if target_index < len(path_parts) and re.fullmatch(r"[A-Za-z0-9._-]+", path_parts[target_index]):
            return target_index
        return None
