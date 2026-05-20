from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.models import PullResult
from app.normalizers.pipeline import normalize_jobs


DEFAULT_OUTPUT_DIR = Path("outputs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize Phase 1 Jobful pull artifacts.")
    parser.add_argument("input", type=Path, help="Path to a Phase 1 PullResult JSON artifact.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to outputs/jobful_normalized_<timestamp>.json.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Normalize only the first N jobs.")
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Disable optional Ollama normalization and use deterministic heuristics only.",
    )
    parser.add_argument(
        "--ollama-mode",
        choices=["review", "all"],
        default="review",
        help="Use Ollama only for low-confidence/review records, or force it for all records.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pull = PullResult.model_validate_json(args.input.read_text(encoding="utf-8"))
    jobs = pull.jobs[: args.limit] if args.limit is not None else pull.jobs
    result = normalize_jobs(
        jobs,
        use_ollama=not args.no_ollama,
        ollama_mode=args.ollama_mode,
    )
    output_path = args.output or _default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_path": str(output_path),
                "source_job_count": result.source_job_count,
                "normalized_job_count": result.normalized_job_count,
                "duplicate_job_count": result.duplicate_job_count,
                "status_counts": result.status_counts,
            },
            indent=2,
        )
    )
    return 0


def _default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"jobful_normalized_{timestamp}.json"


if __name__ == "__main__":
    raise SystemExit(main())
