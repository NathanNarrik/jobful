from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


JobKey = str | tuple[str | None, str | None, str | None]


def job_key(job: dict[str, Any]) -> JobKey:
    return job.get("content_hash") or (
        job.get("ats_provider"),
        job.get("ats_job_id"),
        job.get("job_url"),
    )


def source_matches_token(source: dict[str, Any], tokens: set[str]) -> bool:
    board_token = str(source.get("board_token") or "").lower()
    return board_token in tokens


def job_matches_replacement(
    job: dict[str, Any],
    tokens: set[str],
    company_by_token: dict[str, str],
) -> str | None:
    company_name = str(job.get("company_name") or "").casefold()
    for token, expected_company in company_by_token.items():
        if company_name == expected_company.casefold():
            return token

    haystack = " ".join(
        str(job.get(field) or "")
        for field in ("company_name", "job_url", "ats_provider", "ats_job_id")
    ).lower()
    broad_tokens = tokens - set(company_by_token)
    return next((token for token in broad_tokens if token in haystack), None)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_outputs(
    primary: dict[str, Any],
    fallback: dict[str, Any],
    replace_tokens: set[str],
    company_by_token: dict[str, str],
) -> tuple[dict[str, Any], dict[str, int]]:
    fallback_sources = {
        str(source.get("board_token") or "").lower(): source
        for source in fallback.get("sources", [])
        if source_matches_token(source, replace_tokens)
        and source.get("status") == "success"
    }

    final_sources = [
        source
        for source in primary.get("sources", [])
        if not source_matches_token(source, replace_tokens)
    ]
    final_sources.extend(
        fallback_sources[token]
        for token in sorted(fallback_sources)
        if token in fallback_sources
    )

    final_failures = [
        failure
        for failure in primary.get("failures", [])
        if not source_matches_token(failure, replace_tokens)
    ]

    seen = {job_key(job) for job in primary.get("jobs", [])}
    final_jobs = list(primary.get("jobs", []))
    added_by_token: dict[str, int] = {}

    for job in fallback.get("jobs", []):
        token = job_matches_replacement(job, replace_tokens, company_by_token)
        if token is None:
            continue

        key = job_key(job)
        if key in seen:
            continue

        seen.add(key)
        final_jobs.append(job)
        added_by_token[token] = added_by_token.get(token, 0) + 1

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_count": len(final_sources),
        "successful_source_count": sum(
            1 for source in final_sources if source.get("status") == "success"
        ),
        "failed_source_count": sum(
            1 for source in final_sources if source.get("status") != "success"
        ),
        "job_count": len(final_jobs),
        "sources": final_sources,
        "jobs": final_jobs,
        "failures": final_failures,
    }
    return result, added_by_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge a partial Jobful output with known-good fallback sources."
    )
    parser.add_argument("primary", type=Path)
    parser.add_argument("fallback", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument(
        "--replace-token",
        action="append",
        default=[],
        help="Board token to replace from fallback. May be supplied multiple times.",
    )
    parser.add_argument(
        "--replace-company",
        action="append",
        default=[],
        metavar="TOKEN=COMPANY",
        help="Exact fallback company name for a token. Avoids broad substring matches.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    replace_tokens = {token.lower() for token in args.replace_token}
    if not replace_tokens:
        raise SystemExit("At least one --replace-token is required")
    company_by_token: dict[str, str] = {}
    for item in args.replace_company:
        token, separator, company_name = item.partition("=")
        if not separator or not token or not company_name:
            raise SystemExit(f"Invalid --replace-company value: {item!r}")
        company_by_token[token.lower()] = company_name

    result, added_by_token = merge_outputs(
        load_json(args.primary),
        load_json(args.fallback),
        replace_tokens,
        company_by_token,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"wrote {args.output}")
    print(
        json.dumps(
            {
                "source_count": result["source_count"],
                "successful_source_count": result["successful_source_count"],
                "failed_source_count": result["failed_source_count"],
                "job_count": result["job_count"],
                "added_by_token": added_by_token,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
