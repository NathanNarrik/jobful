from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Type
from urllib.parse import parse_qs, urlparse

from extractors.base import BaseExtractor
from extractors.amazon import AmazonExtractor
from extractors.apple import AppleExtractor
from extractors.ashby import AshbyExtractor
from extractors.avature import AvatureRssExtractor
from extractors.google import GoogleExtractor
from extractors.greenhouse import GreenhouseExtractor
from extractors.lever import LeverExtractor
from extractors.oracle import OracleExtractor
from extractors.talentbrew import TalentBrewExtractor
from extractors.workday import WorkdayExtractor
from models import JobListing


class UnsupportedAtsError(ValueError):
    """Raised when a career URL cannot be routed to a supported ATS provider."""


@dataclass(frozen=True)
class AtsRoute:
    provider: str
    board_token: str
    extractor_class: Type[BaseExtractor]
    source_url: str


class AtsRouter:
    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def route(self, career_url: str) -> AtsRoute:
        parsed = urlparse(career_url)
        hostname = (parsed.hostname or "").lower()
        path_parts = [part for part in parsed.path.split("/") if part]

        if self._is_greenhouse(hostname):
            token = self._greenhouse_token(hostname, path_parts)
            return AtsRoute("greenhouse", token, GreenhouseExtractor, career_url)

        if self._is_lever(hostname):
            token = self._lever_token(hostname, path_parts, parsed.query)
            return AtsRoute("lever", token, LeverExtractor, career_url)

        if self._is_ashby(hostname):
            token = self._ashby_token(hostname, path_parts)
            return AtsRoute("ashby", token, AshbyExtractor, career_url)

        if self._is_workday(hostname):
            token = self._workday_token(hostname)
            return AtsRoute("workday", token, WorkdayExtractor, career_url)

        if self._is_amazon(hostname):
            return AtsRoute("amazon", "amazon", AmazonExtractor, career_url)

        if self._is_google(hostname, path_parts):
            return AtsRoute("google", "google", GoogleExtractor, career_url)

        if self._is_apple(hostname, path_parts):
            return AtsRoute("apple", "apple", AppleExtractor, career_url)

        if self._is_talentbrew(hostname, path_parts):
            return AtsRoute("talentbrew", self._hostname_token(hostname), TalentBrewExtractor, career_url)

        if self._is_avature(hostname, path_parts):
            return AtsRoute("avature", self._hostname_token(hostname), AvatureRssExtractor, career_url)

        if self._is_oracle_recruiting(hostname, path_parts):
            token = self._oracle_token(hostname, path_parts)
            return AtsRoute("oracle", token, OracleExtractor, career_url)

        raise UnsupportedAtsError(f"Unsupported or unrecognized ATS URL: {career_url}")

    def extract(self, career_url: str) -> list[JobListing]:
        route = self.route(career_url)
        self.logger.info("Routing %s to %s board %s", career_url, route.provider, route.board_token)
        return route.extractor_class(
            route.board_token,
            source_url=route.source_url,
            timeout_seconds=self.timeout_seconds,
        ).extract()

    def detect_only(self, career_url: str) -> AtsRoute:
        return self.route(career_url)

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

    def _is_ashby(self, hostname: str) -> bool:
        return hostname in {"jobs.ashbyhq.com", "api.ashbyhq.com"} or hostname.endswith(".ashbyhq.com")

    def _ashby_token(self, hostname: str, path_parts: list[str]) -> str:
        if hostname == "api.ashbyhq.com":
            board_index = self._index_after(path_parts, "job-board")
            if board_index is not None:
                return path_parts[board_index]

        if path_parts:
            return path_parts[0]

        subdomain = hostname.removesuffix(".ashbyhq.com")
        if subdomain and subdomain not in {"jobs", "api"}:
            return subdomain

        raise UnsupportedAtsError("Could not determine Ashby board token")

    def _is_workday(self, hostname: str) -> bool:
        return hostname.endswith(".myworkdayjobs.com")

    def _workday_token(self, hostname: str) -> str:
        token = hostname.split(".", maxsplit=1)[0]
        if token:
            return token
        raise UnsupportedAtsError("Could not determine Workday board token")

    def _is_amazon(self, hostname: str) -> bool:
        return hostname == "www.amazon.jobs" or hostname == "amazon.jobs"

    def _is_google(self, hostname: str, path_parts: list[str]) -> bool:
        return hostname in {"www.google.com", "careers.google.com"} and "careers" in path_parts

    def _is_apple(self, hostname: str, path_parts: list[str]) -> bool:
        return hostname == "jobs.apple.com" and "search" in path_parts

    def _is_oracle_recruiting(self, hostname: str, path_parts: list[str]) -> bool:
        return bool(path_parts) and ("careers" in hostname or hostname.endswith(".oraclecloud.com"))

    def _oracle_token(self, hostname: str, path_parts: list[str]) -> str:
        if "sites" in path_parts:
            site_index = self._index_after(path_parts, "sites")
            if site_index is not None:
                return path_parts[site_index]
        return hostname.split(".", maxsplit=1)[0]

    def _is_talentbrew(self, hostname: str, path_parts: list[str]) -> bool:
        return hostname in {"careers.blackrock.com", "jobs.citi.com"} and "search-jobs" in path_parts

    def _is_avature(self, hostname: str, path_parts: list[str]) -> bool:
        return hostname == "careers.twosigma.com" and "careers" in path_parts

    def _hostname_token(self, hostname: str) -> str:
        return hostname.split(".", maxsplit=1)[0]

    def _index_after(self, path_parts: list[str], marker: str) -> int | None:
        try:
            marker_index = path_parts.index(marker)
        except ValueError:
            return None

        target_index = marker_index + 1
        if target_index < len(path_parts) and re.fullmatch(r"[A-Za-z0-9._-]+", path_parts[target_index]):
            return target_index
        return None
