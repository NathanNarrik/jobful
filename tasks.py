from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import redis
from celery.exceptions import MaxRetriesExceededError

from celery_app import REDIS_URL
from celery_app import celery_app
from cli.extract import dedupe_urls, extract_single_url
from models import JobListing
from normalizers.pipeline import normalize_jobs
from queueing import QueueName, choose_queue, get_backoff_delay
from sources import DEFAULT_CAREER_URLS


RETRYABLE_ERRORS = {
    "ConnectionError",
    "ExtractionError",
    "RateLimitedError",
    "ReadTimeout",
    "Timeout",
}

QUEUE_LOCK_TTL_SECONDS = {
    QueueName.HIGH: 60 * 60,
    QueueName.STANDARD: 4 * 60 * 60,
    QueueName.SLOW: 12 * 60 * 60,
}

DEAD_LETTER_REDIS_KEY = "jobful:dead_letters"
DEFAULT_DEAD_LETTER_PATH = Path("outputs/dead_letters.jsonl")


@celery_app.task(bind=True, name="jobful.extract_source", max_retries=3)
def extract_source(
    self: Any,
    career_url: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    jobs, failure, source_result = extract_single_url(career_url, timeout_seconds)

    if failure and failure.error_type in RETRYABLE_ERRORS:
        try:
            raise self.retry(countdown=get_backoff_delay(self.request.retries + 1))
        except MaxRetriesExceededError:
            record_dead_letter.apply_async(
                args=[failure.model_dump(mode="json")],
                queue=QueueName.DEAD_LETTER.value,
                routing_key=QueueName.DEAD_LETTER.value,
            )

    return {
        "source": source_result.model_dump(mode="json"),
        "jobs": [job.model_dump(mode="json") for job in jobs],
        "failure": failure.model_dump(mode="json") if failure else None,
    }


@celery_app.task(name="jobful.normalize_jobs")
def normalize_jobs_task(
    jobs_payload: list[dict[str, Any]],
    *,
    use_ollama: bool = True,
    ollama_mode: str = "review",
) -> dict[str, Any]:
    jobs = [JobListing.model_validate(job_payload) for job_payload in jobs_payload]
    result = normalize_jobs(jobs, use_ollama=use_ollama, ollama_mode=ollama_mode)
    return result.model_dump(mode="json")


@celery_app.task(name="jobful.extract_and_normalize_source")
def extract_and_normalize_source(
    career_url: str,
    timeout_seconds: float = 10.0,
    *,
    use_ollama: bool = True,
    ollama_mode: str = "review",
) -> dict[str, Any]:
    extraction = extract_source.run(career_url, timeout_seconds)
    if extraction["failure"] is not None:
        return {
            "source": extraction["source"],
            "failure": extraction["failure"],
            "normalization": None,
        }

    normalization = normalize_jobs_task.run(
        extraction["jobs"],
        use_ollama=use_ollama,
        ollama_mode=ollama_mode,
    )
    return {
        "source": extraction["source"],
        "failure": None,
        "normalization": normalization,
    }


@celery_app.task(name="jobful.enqueue_urls")
def enqueue_urls(
    career_urls: list[str],
    *,
    target_queue: str | None = None,
    timeout_seconds: float = 10.0,
    use_locks: bool = True,
) -> dict[str, Any]:
    enqueued: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    lock_client = _redis_client() if use_locks else None

    for career_url in dedupe_urls(career_urls):
        queue_name = QueueName(target_queue) if target_queue else choose_queue(career_url).queue
        if lock_client and not _acquire_enqueue_lock(lock_client, career_url, queue_name):
            skipped.append(
                {
                    "career_url": career_url,
                    "queue": queue_name.value,
                    "reason": "recently enqueued",
                }
            )
            continue

        async_result = extract_source.apply_async(
            args=[career_url, timeout_seconds],
            queue=queue_name.value,
            routing_key=queue_name.value,
        )
        enqueued.append(
            {
                "career_url": career_url,
                "queue": queue_name.value,
                "task_id": async_result.id,
            }
        )

    return {
        "enqueued_at": datetime.now(UTC).isoformat(),
        "count": len(enqueued),
        "skipped_count": len(skipped),
        "items": enqueued,
        "skipped": skipped,
    }


@celery_app.task(name="jobful.enqueue_default_sources")
def enqueue_default_sources(
    *,
    target_queue: str | None = None,
    timeout_seconds: float = 10.0,
    use_locks: bool = True,
) -> dict[str, Any]:
    selected_urls = _urls_for_target_queue(DEFAULT_CAREER_URLS, target_queue)
    return enqueue_urls.run(
        selected_urls,
        target_queue=target_queue,
        timeout_seconds=timeout_seconds,
        use_locks=use_locks,
    )


@celery_app.task(name="jobful.record_dead_letter")
def record_dead_letter(failure: dict[str, Any]) -> dict[str, Any]:
    record = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "failure": failure,
    }
    _append_dead_letter(record)
    _record_dead_letter_to_redis(record)
    return record


def _urls_for_target_queue(career_urls: list[str], target_queue: str | None) -> list[str]:
    if target_queue is None:
        return career_urls

    queue = QueueName(target_queue)
    return [
        career_url
        for career_url in career_urls
        if choose_queue(career_url).queue == queue
    ]


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _acquire_enqueue_lock(
    client: redis.Redis,
    career_url: str,
    queue_name: QueueName,
) -> bool:
    key = f"jobful:enqueue-lock:{queue_name.value}:{career_url}"
    ttl = QUEUE_LOCK_TTL_SECONDS.get(queue_name, 60 * 60)
    return bool(client.set(key, "1", nx=True, ex=ttl))


def _append_dead_letter(record: dict[str, Any]) -> None:
    path = Path(os.getenv("JOBFUL_DEAD_LETTER_PATH", str(DEFAULT_DEAD_LETTER_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _record_dead_letter_to_redis(record: dict[str, Any]) -> None:
    try:
        client = _redis_client()
        client.lpush(DEAD_LETTER_REDIS_KEY, json.dumps(record, ensure_ascii=False))
        client.ltrim(DEAD_LETTER_REDIS_KEY, 0, 999)
    except redis.RedisError:
        return
