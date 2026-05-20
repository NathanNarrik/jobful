from __future__ import annotations

import itertools
import logging
import os
from pathlib import Path

import redis


DEFAULT_BAN_TTL_SECONDS = 24 * 60 * 60


class ProxyPool:
    def __init__(self, proxy_urls: list[str]) -> None:
        self.proxy_urls = proxy_urls
        self._cycle = itertools.cycle(proxy_urls) if proxy_urls else None
        self._last_proxy_url: str | None = None
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @classmethod
    def from_environment(cls) -> ProxyPool:
        proxy_urls = _proxy_urls_from_env()
        proxy_file = os.getenv("JOBFUL_PROXY_FILE")
        if proxy_file:
            proxy_urls.extend(_proxy_urls_from_file(Path(proxy_file)))
        return cls(_dedupe(proxy_urls))

    def next_requests_proxy(self) -> dict[str, str] | None:
        if self._cycle is None:
            return None

        proxy_url = self._next_available_proxy_url()
        if proxy_url is None:
            return None

        self._last_proxy_url = proxy_url
        return {
            "http": proxy_url,
            "https": proxy_url,
        }

    def mark_current_proxy_banned(self, *, ttl_seconds: int = DEFAULT_BAN_TTL_SECONDS) -> None:
        if self._last_proxy_url is None:
            return

        try:
            client = _redis_client()
            client.set(_ban_key(self._last_proxy_url), "1", ex=ttl_seconds)
        except redis.RedisError:
            self._logger.debug("Could not persist proxy ban status", exc_info=True)

    def _next_available_proxy_url(self) -> str | None:
        if self._cycle is None:
            return None

        for _ in range(len(self.proxy_urls)):
            proxy_url = next(self._cycle)
            if not _is_proxy_banned(proxy_url):
                return proxy_url
        return None


def _proxy_urls_from_env() -> list[str]:
    raw_value = os.getenv("JOBFUL_PROXY_URLS", "")
    return [
        proxy_url.strip()
        for proxy_url in raw_value.replace("\n", ",").split(",")
        if proxy_url.strip()
    ]


def _proxy_urls_from_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _is_proxy_banned(proxy_url: str) -> bool:
    try:
        return bool(_redis_client().exists(_ban_key(proxy_url)))
    except redis.RedisError:
        return False


def _ban_key(proxy_url: str) -> str:
    return f"proxy:{proxy_url}:banned"


def _redis_client() -> redis.Redis:
    redis_url = os.getenv("JOBFUL_REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url, decode_responses=True)
