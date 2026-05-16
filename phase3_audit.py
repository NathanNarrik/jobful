from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

from models import NormalizationResult, NormalizedJobRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a manual audit sample from a Phase 3 artifact.")
    parser.add_argument("input", type=Path, help="Path to a Phase 3 NormalizationResult JSON artifact.")
    parser.add_argument("-o", "--output", type=Path, required=True, help="CSV audit sample output path.")
    parser.add_argument("--sample-size", type=int, default=100, help="Number of records to sample.")
    parser.add_argument("--seed", type=int, default=42, help="Random sample seed.")
    parser.add_argument(
        "--needs-review-only",
        action="store_true",
        help="Sample only records with normalization_status=NEEDS_REVIEW.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = NormalizationResult.model_validate_json(args.input.read_text(encoding="utf-8"))
    records = result.records
    if args.needs_review_only:
        records = [
            record
            for record in records
            if record.normalization.normalization_status == "NEEDS_REVIEW"
        ]

    sample = _sample(records, args.sample_size, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=_fieldnames())
        writer.writeheader()
        for record in sample:
            writer.writerow(_row(record))

    print(json.dumps({"output_path": str(args.output), "sample_count": len(sample)}, indent=2))
    return 0


def _sample(records: list[NormalizedJobRecord], sample_size: int, seed: int) -> list[NormalizedJobRecord]:
    if sample_size >= len(records):
        return records
    rng = random.Random(seed)
    return rng.sample(records, sample_size)


def _row(record: NormalizedJobRecord) -> dict[str, Any]:
    return {
        "company_name": record.job.company_name,
        "job_title": record.job.job_title,
        "job_url": str(record.job.job_url),
        "program_type": record.normalization.program_type,
        "academic_levels": "|".join(record.normalization.academic_levels),
        "degree_requirements": "|".join(record.normalization.degree_requirements),
        "required_grad_years": "|".join(str(year) for year in record.normalization.required_grad_years),
        "visa_status": record.normalization.visa_status,
        "remote_type": record.normalization.remote_type,
        "required_skills": "|".join(record.normalization.required_skills),
        "confidence": record.normalization.confidence,
        "normalization_status": record.normalization.normalization_status,
        "review_reasons": "|".join(record.normalization.review_reasons),
        "description_preview": record.cleaned_description[:500].replace("\n", " "),
        "human_notes": "",
    }


def _fieldnames() -> list[str]:
    return [
        "company_name",
        "job_title",
        "job_url",
        "program_type",
        "academic_levels",
        "degree_requirements",
        "required_grad_years",
        "visa_status",
        "remote_type",
        "required_skills",
        "confidence",
        "normalization_status",
        "review_reasons",
        "description_preview",
        "human_notes",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
