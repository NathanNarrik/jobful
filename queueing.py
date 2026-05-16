from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum


class QueueName(StrEnum):
    HIGH = "jobful:high"
    STANDARD = "jobful:standard"
    SLOW = "jobful:slow"
    DEAD_LETTER = "jobful:dead_letter"


HIGH_PRIORITY_COMPANY_MARKERS = {
    "amazon",
    "anthropic",
    "apple",
    "cloudflare",
    "databricks",
    "datadog",
    "doordash",
    "google",
    "meta",
    "microsoft",
    "netflix",
    "nvidia",
    "openai",
    "pinterest",
    "roblox",
    "stripe",
}

SLOW_PRIORITY_PROVIDER_MARKERS = {
    "ashbyhq.com",
    "myworkdayjobs.com",
}


@dataclass(frozen=True)
class QueueDecision:
    queue: QueueName
    reason: str


def get_backoff_delay(attempt: int, base: float = 2.0, cap: float = 300.0) -> float:
    delay = min(base**attempt, cap)
    jitter = random.uniform(0.0, delay * 0.1)
    return delay + jitter


def choose_queue(career_url: str) -> QueueDecision:
    normalized = career_url.lower()

    if any(marker in normalized for marker in HIGH_PRIORITY_COMPANY_MARKERS):
        return QueueDecision(QueueName.HIGH, "high-priority company")

    if any(marker in normalized for marker in SLOW_PRIORITY_PROVIDER_MARKERS):
        return QueueDecision(QueueName.SLOW, "slower or browser-heavy ATS")

    return QueueDecision(QueueName.STANDARD, "default cadence")
