from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from app.cli.extract import read_url_file
from app.router import AtsRouter, UnsupportedAtsError
from app.sources import DEFAULT_CAREER_URLS


@dataclass(frozen=True)
class SourceCountAudit:
    source_url: str
    provider: str | None
    board_token: str | None
    expected_count: int | None
    status: str
    message: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit default career sources against public ATS count endpoints.")
    parser.add_argument("-i", "--input-file", type=Path, help="Optional newline-delimited source URL file.")
    parser.add_argument("-o", "--output", type=Path, help="Optional JSON output path.")
    parser.add_argument("--limit", type=int, default=None, help="Only check the first N sources.")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=8.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    urls = read_url_file(args.input_file) if args.input_file else DEFAULT_CAREER_URLS
    if args.limit is not None:
        urls = urls[: args.limit]

    results = audit_sources(urls, workers=args.workers, timeout=args.timeout)
    payload = {
        "source_count": len(urls),
        "audited_count": len(results),
        "counted_count": sum(1 for result in results if result.expected_count is not None),
        "unsupported_count": sum(1 for result in results if result.status == "unsupported_count_probe"),
        "failed_count": sum(1 for result in results if result.status == "failed"),
        "results": [asdict(result) for result in results],
    }
    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


def audit_sources(career_urls: list[str], *, workers: int, timeout: float) -> list[SourceCountAudit]:
    router = AtsRouter(timeout_seconds=timeout)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(audit_source, router, career_url, timeout) for career_url in career_urls]
        return [future.result() for future in as_completed(futures)]


def audit_source(router: AtsRouter, career_url: str, timeout: float) -> SourceCountAudit:
    try:
        route = router.detect_only(career_url)
    except UnsupportedAtsError as exc:
        return SourceCountAudit(career_url, None, None, None, "failed", str(exc))

    try:
        expected = expected_count(route.provider, route.board_token, timeout)
    except requests.RequestException as exc:
        return SourceCountAudit(career_url, route.provider, route.board_token, None, "failed", str(exc))
    except ValueError as exc:
        return SourceCountAudit(career_url, route.provider, route.board_token, None, "failed", str(exc))

    if expected is None:
        return SourceCountAudit(career_url, route.provider, route.board_token, None, "unsupported_count_probe")
    return SourceCountAudit(career_url, route.provider, route.board_token, expected, "counted")


def expected_count(provider: str, board_token: str, timeout: float) -> int | None:
    if provider == "greenhouse":
        payload = get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{quote(board_token)}/jobs?content=false",
            timeout,
        )
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise ValueError("Greenhouse payload did not include jobs list")
        return len(jobs)

    if provider == "lever":
        payload = get_json(f"https://api.lever.co/v0/postings/{quote(board_token)}?mode=json", timeout)
        if not isinstance(payload, list):
            raise ValueError("Lever payload was not a list")
        return len(payload)

    if provider == "ashby":
        payload = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{quote(board_token)}", timeout)
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise ValueError("Ashby payload did not include jobs list")
        return len([job for job in jobs if isinstance(job, dict) and job.get("isListed") is not False])

    if provider == "smartrecruiters":
        payload = get_json(
            f"https://api.smartrecruiters.com/v1/companies/{quote(board_token)}/postings?limit=1&offset=0",
            timeout,
        )
        total = payload.get("totalFound")
        return int(total) if total is not None else None

    return None


def get_json(url: str, timeout: float) -> Any:
    last_error: requests.RequestException | None = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers={"User-Agent": "JobfulSourceAudit/1.0"}, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


if __name__ == "__main__":
    raise SystemExit(main())
