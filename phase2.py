from __future__ import annotations

import argparse
import json
from pathlib import Path

from main import dedupe_urls, read_url_file
from queueing import QueueName, choose_queue
from sources import DEFAULT_CAREER_URLS
from tasks import enqueue_default_sources, enqueue_urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enqueue Jobful extraction work into Redis/Celery.")
    parser.add_argument("career_urls", nargs="*", help="Optional career URLs to enqueue.")
    parser.add_argument("-i", "--input-file", type=Path, help="Newline-delimited career URL file.")
    parser.add_argument(
        "--include-defaults",
        action="store_true",
        help="Also enqueue the default source list.",
    )
    parser.add_argument(
        "--queue",
        choices=[queue.value for queue in QueueName if queue is not QueueName.DEAD_LETTER],
        default=None,
        help="Force all enqueued URLs onto one queue. Defaults to priority classification.",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Extractor timeout in seconds.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print queue decisions without connecting to Redis.",
    )
    parser.add_argument(
        "--no-locks",
        action="store_true",
        help="Bypass Redis enqueue locks and submit duplicate URLs again.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    urls = list(args.career_urls)
    if args.input_file:
        urls.extend(read_url_file(args.input_file))

    if args.dry_run:
        planned_urls = []
        if args.include_defaults or not urls:
            planned_urls.extend(DEFAULT_CAREER_URLS)
        planned_urls.extend(urls)
        print(json.dumps(_dry_run(dedupe_urls(planned_urls), args.queue), indent=2))
        return 0

    summaries = []
    if args.include_defaults or not urls:
        result = enqueue_default_sources.delay(
            target_queue=args.queue,
            timeout_seconds=args.timeout,
            use_locks=not args.no_locks,
        )
        summaries.append({"task": "enqueue_default_sources", "task_id": result.id})

    if urls:
        result = enqueue_urls.delay(
            urls,
            target_queue=args.queue,
            timeout_seconds=args.timeout,
            use_locks=not args.no_locks,
        )
        summaries.append({"task": "enqueue_urls", "task_id": result.id})

    print(json.dumps({"submitted": summaries}, indent=2))
    return 0


def _dry_run(career_urls: list[str], target_queue: str | None) -> dict[str, object]:
    items = []
    for career_url in career_urls:
        decision = choose_queue(career_url)
        queue_name = target_queue or decision.queue.value
        items.append(
            {
                "career_url": career_url,
                "queue": queue_name,
                "reason": "forced queue" if target_queue else decision.reason,
            }
        )
    return {
        "mode": "dry_run",
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    raise SystemExit(main())
