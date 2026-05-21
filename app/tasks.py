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
from app.cli.extract import dedupe_urls, extract_single_url
from app.db.import_phase3 import import_result
from app.db.mark_stale import mark_stale
from app.db.session import SessionLocal
from app.events.db.import_events import import_events
from app.events.db.session import EventsSessionLocal
from app.events.extract import extract_single_event_source
from app.events.sources import DEFAULT_EVENT_SOURCES
from app.models import JobListing
from app.models import EventSourceConfig
from app.models import NormalizationResult
from app.models import RecruitingEventListing
from app.normalizers.pipeline import normalize_jobs
from app.queueing import QueueName, choose_queue, get_backoff_delay
from app.sources import DEFAULT_CAREER_URLS


RETRYABLE_ERRORS = {
    "ConnectionError",
    "ExtractionError",
    "RateLimitedError",
    "ReadTimeout",
    "Timeout",
}

DEFAULT_REFRESH_LOCK_SECONDS = 30 * 60

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


@celery_app.task(name="jobful.extract_normalize_import_source")
def extract_normalize_import_source(
    career_url: str,
    timeout_seconds: float = 10.0,
    *,
    use_ollama: bool = False,
    ollama_mode: str = "review",
) -> dict[str, Any]:
    result = extract_and_normalize_source.run(
        career_url,
        timeout_seconds,
        use_ollama=use_ollama,
        ollama_mode=ollama_mode,
    )
    if result["failure"] is not None or result["normalization"] is None:
        return {**result, "import": None}

    normalization = NormalizationResult.model_validate(result["normalization"])
    with SessionLocal() as session:
        import_summary = import_result(session, normalization)

    return {
        **result,
        "import": import_summary.to_dict(),
    }


@celery_app.task(name="jobful.enqueue_urls")
def enqueue_urls(
    career_urls: list[str],
    *,
    target_queue: str | None = None,
    timeout_seconds: float = 10.0,
    use_locks: bool = True,
    import_to_db: bool = True,
    use_ollama: bool = False,
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

        task = extract_normalize_import_source if import_to_db else extract_source
        kwargs: dict[str, Any] = {}
        if import_to_db:
            kwargs["use_ollama"] = use_ollama
        async_result = task.apply_async(
            args=[career_url, timeout_seconds],
            kwargs=kwargs,
            queue=queue_name.value,
            routing_key=queue_name.value,
        )
        enqueued.append(
            {
                "career_url": career_url,
                "queue": queue_name.value,
                "task_id": async_result.id,
                "task": task.name,
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
    import_to_db: bool = True,
    use_ollama: bool = False,
) -> dict[str, Any]:
    selected_urls = _urls_for_target_queue(DEFAULT_CAREER_URLS, target_queue)
    return enqueue_urls.run(
        selected_urls,
        target_queue=target_queue,
        timeout_seconds=timeout_seconds,
        use_locks=use_locks,
        import_to_db=import_to_db,
        use_ollama=use_ollama,
    )


@celery_app.task(name="jobful.mark_stale_jobs")
def mark_stale_jobs(*, older_than_hours: int | None = None) -> dict[str, Any]:
    stale_after = older_than_hours
    if stale_after is None:
        stale_after = _env_int("JOBFUL_STALE_AFTER_HOURS", 2)
    with SessionLocal() as session:
        count = mark_stale(session, older_than_hours=stale_after)
    return {
        "marked_at": datetime.now(UTC).isoformat(),
        "older_than_hours": stale_after,
        "jobs_marked_inactive": count,
    }


@celery_app.task(bind=True, name="jobful.extract_event_source", max_retries=3)
def extract_event_source(
    self: Any,
    source_payload: dict[str, Any],
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    source = EventSourceConfig.model_validate(source_payload)
    events, failure, source_result = extract_single_event_source(source, timeout_seconds)

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
        "events": [event.model_dump(mode="json") for event in events],
        "failure": failure.model_dump(mode="json") if failure else None,
    }


@celery_app.task(name="jobful.extract_and_import_event_source")
def extract_and_import_event_source(
    source_payload: dict[str, Any],
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    source = EventSourceConfig.model_validate(source_payload)
    extraction = extract_event_source.run(source.model_dump(mode="json"), timeout_seconds)
    if extraction["failure"] is not None:
        return {
            "source": extraction["source"],
            "failure": extraction["failure"],
            "import": None,
        }

    with EventsSessionLocal() as session:
        events = [RecruitingEventListing.model_validate(item) for item in extraction["events"]]
        summary = import_events(session, events, source)

    return {
        "source": extraction["source"],
        "failure": None,
        "import": summary.to_dict(),
    }


@celery_app.task(name="jobful.enqueue_default_event_sources")
def enqueue_default_event_sources(
    *,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    enqueued: list[dict[str, str]] = []
    for source in DEFAULT_EVENT_SOURCES:
        async_result = extract_and_import_event_source.apply_async(
            args=[source.model_dump(mode="json"), timeout_seconds],
            queue=QueueName.STANDARD.value,
            routing_key=QueueName.STANDARD.value,
        )
        enqueued.append(
            {
                "source_url": str(source.event_page_url),
                "firm_name": source.firm_name,
                "task_id": async_result.id,
            }
        )

    return {
        "enqueued_at": datetime.now(UTC).isoformat(),
        "count": len(enqueued),
        "items": enqueued,
    }


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
    ttl = _env_int("JOBFUL_REFRESH_LOCK_SECONDS", DEFAULT_REFRESH_LOCK_SECONDS)
    return bool(client.set(key, "1", nx=True, ex=ttl))


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


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
