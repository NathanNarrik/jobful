from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from app.models import JobListing, PullFailure, PullResult, PullSourceResult
from app.router import AtsRouter, UnsupportedAtsError
from app.sources import DEFAULT_CAREER_URLS


DEFAULT_OUTPUT_DIR = Path("outputs")


def extract_urls(
    career_urls: Iterable[str],
    *,
    timeout_seconds: float = 10.0,
    workers: int = 8,
) -> PullResult:
    urls = dedupe_urls(career_urls)
    listings: list[JobListing] = []
    failures: list[PullFailure] = []
    source_results: list[PullSourceResult] = []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(extract_single_url, career_url, timeout_seconds): career_url
            for career_url in urls
        }

        for future in as_completed(futures):
            career_url = futures[future]
            jobs, failure, source_result = future.result()
            source_results.append(source_result)
            if failure is not None:
                logging.warning(
                    "Source skipped: %s (%s: %s)",
                    career_url,
                    failure.error_type,
                    failure.message,
                )
                failures.append(failure)
                continue

            logging.info("Extracted %s jobs from %s", len(jobs), career_url)
            listings.extend(jobs)

    return PullResult(
        generated_at=datetime.now(UTC),
        source_count=len(urls),
        successful_source_count=len(urls) - len(failures),
        failed_source_count=len(failures),
        job_count=len(listings),
        sources=sorted(source_results, key=lambda source: source.source_url.lower()),
        jobs=listings,
        failures=failures,
    )


def extract_single_url(
    career_url: str,
    timeout_seconds: float,
) -> tuple[list[JobListing], PullFailure | None, PullSourceResult]:
    router = AtsRouter(timeout_seconds=timeout_seconds)
    provider: str | None = None
    board_token: str | None = None

    try:
        route = router.route(career_url)
        provider = route.provider
        board_token = route.board_token
        jobs = route.extractor_class(
            board_token,
            source_url=route.source_url,
            timeout_seconds=timeout_seconds,
        ).extract()
        return jobs, None, PullSourceResult(
            source_url=career_url,
            ats_provider=provider,
            board_token=board_token,
            status="success",
            job_count=len(jobs),
        )
    except UnsupportedAtsError as exc:
        logging.exception("Unsupported ATS URL skipped: %s", career_url)
        failure = PullFailure(
            source_url=career_url,
            ats_provider=provider,
            board_token=board_token,
            error_type=exc.__class__.__name__,
            message=str(exc),
        )
        return [], failure, PullSourceResult(
            source_url=career_url,
            ats_provider=provider,
            board_token=board_token,
            status="failed",
            job_count=0,
            error_type=failure.error_type,
            message=failure.message,
        )
    except Exception as exc:
        logging.exception("Extraction failed for URL skipped: %s", career_url)
        failure = PullFailure(
            source_url=career_url,
            ats_provider=provider,
            board_token=board_token,
            error_type=exc.__class__.__name__,
            message=str(exc),
        )
        return [], failure, PullSourceResult(
            source_url=career_url,
            ats_provider=provider,
            board_token=board_token,
            status="failed",
            job_count=0,
            error_type=failure.error_type,
            message=failure.message,
        )


def dedupe_urls(career_urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []

    for career_url in career_urls:
        normalized = career_url.strip().lstrip("\ufeff")
        if not normalized or normalized.startswith("#") or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    return deduped


def read_url_file(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"jobful_pull_{timestamp}.json"


def write_result(result: PullResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull active jobs directly from ATS JSON APIs.")
    parser.add_argument("career_urls", nargs="*", help="Optional ATS career URLs to pull instead of defaults.")
    parser.add_argument(
        "-i",
        "--input-file",
        type=Path,
        help="Optional newline-delimited file of ATS career URLs.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to outputs/jobful_pull_<timestamp>.json.",
    )
    parser.add_argument(
        "--include-defaults",
        action="store_true",
        help="Merge default seed URLs with URLs passed through args or --input-file.",
    )
    parser.add_argument("--workers", type=int, default=8, help="Concurrent source pulls.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Also print the full JSON artifact to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    career_urls: list[str] = []
    custom_urls_requested = bool(args.career_urls or args.input_file)

    if not custom_urls_requested or args.include_defaults:
        career_urls.extend(DEFAULT_CAREER_URLS)
    if args.input_file:
        career_urls.extend(read_url_file(args.input_file))
    career_urls.extend(args.career_urls)

    result = extract_urls(
        career_urls,
        timeout_seconds=args.timeout,
        workers=args.workers,
    )

    output_path = args.output or default_output_path()
    write_result(result, output_path)

    summary = {
        "output_path": str(output_path),
        "source_count": result.source_count,
        "successful_source_count": result.successful_source_count,
        "failed_source_count": result.failed_source_count,
        "job_count": result.job_count,
    }
    print(json.dumps(summary, indent=2))

    if args.print_json:
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))

    return 0


class CompanyLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "company"):
            record.company = "-"
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(CompanyLogFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(company)s] - %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


if __name__ == "__main__":
    raise SystemExit(main())
