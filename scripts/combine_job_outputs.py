from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def job_key(job: dict[str, Any]) -> str | tuple[str | None, str | None, str | None]:
    return job.get("content_hash") or (
        job.get("ats_provider"),
        job.get("ats_job_id"),
        job.get("job_url"),
    )


def source_key(source: dict[str, Any]) -> tuple[str | None, str | None, str]:
    return (
        source.get("ats_provider"),
        source.get("board_token"),
        str(source.get("source_url") or ""),
    )


def load_output(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def combine_outputs(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    sources_by_key: dict[tuple[str | None, str | None, str], dict[str, Any]] = {}
    jobs_by_key: dict[str | tuple[str | None, str | None, str | None], dict[str, Any]] = {}
    failures_by_source: dict[str, dict[str, Any]] = {}

    for output in outputs:
        for source in output.get("sources", []):
            key = source_key(source)
            existing = sources_by_key.get(key)
            if existing is None or existing.get("status") != "success":
                sources_by_key[key] = source

        for job in output.get("jobs", []):
            jobs_by_key.setdefault(job_key(job), job)

        for failure in output.get("failures", []):
            failures_by_source[str(failure.get("source_url") or "")] = failure

    sources = sorted(
        sources_by_key.values(),
        key=lambda source: str(source.get("source_url") or "").lower(),
    )
    successful_source_urls = {
        str(source.get("source_url") or "")
        for source in sources
        if source.get("status") == "success"
    }
    failures = [
        failure
        for source_url, failure in sorted(failures_by_source.items())
        if source_url not in successful_source_urls
    ]
    jobs = list(jobs_by_key.values())

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_count": len(sources),
        "successful_source_count": sum(1 for source in sources if source.get("status") == "success"),
        "failed_source_count": sum(1 for source in sources if source.get("status") != "success"),
        "job_count": len(jobs),
        "sources": sources,
        "jobs": jobs,
        "failures": failures,
    }


def write_company_counts(output: dict[str, Any], path: Path) -> None:
    counts = Counter(str(job.get("company_name") or "Unknown") for job in output.get("jobs", []))
    lines = [
        f"{company}\t{count}"
        for company, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine Jobful pull outputs and dedupe jobs.")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--company-counts-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = combine_outputs([load_output(path) for path in args.inputs])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.company_counts_output:
        args.company_counts_output.parent.mkdir(parents=True, exist_ok=True)
        write_company_counts(output, args.company_counts_output)

    print(
        json.dumps(
            {
                "output": str(args.output),
                "company_counts_output": str(args.company_counts_output)
                if args.company_counts_output
                else None,
                "source_count": output["source_count"],
                "successful_source_count": output["successful_source_count"],
                "failed_source_count": output["failed_source_count"],
                "job_count": output["job_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
