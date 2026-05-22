from __future__ import annotations

import os

from kombu import Exchange, Queue

from app.env import load_local_env
from app.queueing import QueueName


load_local_env()

task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]
timezone = "UTC"
enable_utc = True
broker_connection_retry_on_startup = True
result_expires = 3600
task_track_started = True
worker_prefetch_multiplier = 1
task_acks_late = True

task_default_queue = QueueName.STANDARD.value
task_default_exchange = "jobful"
task_default_routing_key = QueueName.STANDARD.value

task_queues = (
    Queue(QueueName.HIGH.value, Exchange("jobful"), routing_key=QueueName.HIGH.value),
    Queue(QueueName.STANDARD.value, Exchange("jobful"), routing_key=QueueName.STANDARD.value),
    Queue(QueueName.SLOW.value, Exchange("jobful"), routing_key=QueueName.SLOW.value),
    Queue(QueueName.DEAD_LETTER.value, Exchange("jobful"), routing_key=QueueName.DEAD_LETTER.value),
)

task_routes = {
    "jobful.extract_source": {"queue": QueueName.STANDARD.value},
    "jobful.normalize_jobs": {"queue": QueueName.STANDARD.value},
    "jobful.extract_and_normalize_source": {"queue": QueueName.STANDARD.value},
    "jobful.extract_normalize_import_source": {"queue": QueueName.STANDARD.value},
    "jobful.extract_event_source": {"queue": QueueName.STANDARD.value},
    "jobful.extract_and_import_event_source": {"queue": QueueName.STANDARD.value},
    "jobful.enqueue_default_sources": {"queue": QueueName.HIGH.value},
    "jobful.enqueue_default_event_sources": {"queue": QueueName.HIGH.value},
    "jobful.enqueue_urls": {"queue": QueueName.HIGH.value},
    "jobful.mark_stale_jobs": {"queue": QueueName.STANDARD.value},
    "jobful.record_dead_letter": {"queue": QueueName.DEAD_LETTER.value},
}


def _schedule_seconds(env_name: str, default: int) -> int:
    value = os.getenv(env_name)
    if value is None:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


beat_schedule = {
    "enqueue-high-priority-every-two-minutes": {
        "task": "jobful.enqueue_default_sources",
        "schedule": _schedule_seconds("JOBFUL_BEAT_HIGH_SECONDS", 2 * 60),
        "kwargs": {"target_queue": QueueName.HIGH.value},
    },
    "enqueue-standard-every-five-minutes": {
        "task": "jobful.enqueue_default_sources",
        "schedule": _schedule_seconds("JOBFUL_BEAT_STANDARD_SECONDS", 5 * 60),
        "kwargs": {"target_queue": QueueName.STANDARD.value},
    },
    "enqueue-slow-every-ten-minutes": {
        "task": "jobful.enqueue_default_sources",
        "schedule": _schedule_seconds("JOBFUL_BEAT_SLOW_SECONDS", 10 * 60),
        "kwargs": {"target_queue": QueueName.SLOW.value},
    },
    "mark-stale-jobs-every-ten-minutes": {
        "task": "jobful.mark_stale_jobs",
        "schedule": _schedule_seconds("JOBFUL_BEAT_STALE_SECONDS", 10 * 60),
    },
}
