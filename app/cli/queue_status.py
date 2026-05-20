from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import redis

from celery_app import REDIS_URL
from app.queueing import QueueName
from app.tasks import DEAD_LETTER_REDIS_KEY, DEFAULT_DEAD_LETTER_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect Jobful Phase 2 queue and failure status.")
    parser.add_argument("--dead-letter-limit", type=int, default=5, help="Recent dead letters to show.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "redis_url": REDIS_URL,
        "queues": _queue_depths(),
        "dead_letters": _dead_letters(args.dead_letter_limit),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _queue_depths() -> dict[str, int | str]:
    try:
        client = _redis_client()
        return {
            queue.value: client.llen(queue.value)
            for queue in QueueName
        }
    except redis.RedisError as exc:
        return {"error": str(exc)}


def _dead_letters(limit: int) -> dict[str, Any]:
    path = Path(os.getenv("JOBFUL_DEAD_LETTER_PATH", str(DEFAULT_DEAD_LETTER_PATH)))
    records = _dead_letters_from_redis(limit) or _dead_letters_from_file(path, limit)
    return {
        "path": str(path),
        "recent": records,
    }


def _dead_letters_from_redis(limit: int) -> list[dict[str, Any]]:
    try:
        client = _redis_client()
        raw_records = client.lrange(DEAD_LETTER_REDIS_KEY, 0, max(limit - 1, 0))
    except redis.RedisError:
        return []

    records: list[dict[str, Any]] = []
    for raw_record in raw_records:
        try:
            records.append(json.loads(raw_record))
        except json.JSONDecodeError:
            continue
    return records


def _dead_letters_from_file(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


if __name__ == "__main__":
    raise SystemExit(main())
