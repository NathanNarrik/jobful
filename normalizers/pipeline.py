from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from models import JobListing, NormalizationResult, NormalizedJobRecord
from normalizers.cleaner import clean_description
from normalizers.heuristics import heuristic_normalize
from normalizers.ollama import normalize_with_ollama


def normalize_job(
    job: JobListing,
    *,
    use_ollama: bool = True,
    ollama_mode: str = "review",
) -> NormalizedJobRecord:
    cleaned = clean_description(job.raw_description, job.description_html)
    heuristic_normalization = heuristic_normalize(job, cleaned)
    should_try_ollama = (
        use_ollama
        and ollama_mode in {"review", "all"}
        and (
            ollama_mode == "all"
            or heuristic_normalization.normalization_status == "NEEDS_REVIEW"
            or heuristic_normalization.confidence < 0.75
        )
    )
    llm_normalization = normalize_with_ollama(cleaned) if should_try_ollama else None
    if llm_normalization is not None:
        return NormalizedJobRecord(
            job=job,
            cleaned_description=cleaned,
            normalization=llm_normalization,
            normalization_method="ollama",
            normalized_at=datetime.now(UTC),
        )

    return NormalizedJobRecord(
        job=job,
        cleaned_description=cleaned,
        normalization=heuristic_normalization,
        normalization_method="heuristic",
        normalized_at=datetime.now(UTC),
    )


def normalize_jobs(
    jobs: list[JobListing],
    *,
    use_ollama: bool = True,
    ollama_mode: str = "review",
) -> NormalizationResult:
    unique_jobs, duplicate_count = _dedupe_jobs(jobs)
    records = [
        normalize_job(job, use_ollama=use_ollama, ollama_mode=ollama_mode)
        for job in unique_jobs
    ]
    status_counts = Counter(record.normalization.normalization_status for record in records)
    return NormalizationResult(
        generated_at=datetime.now(UTC),
        source_job_count=len(jobs),
        normalized_job_count=len(records),
        duplicate_job_count=duplicate_count,
        status_counts=dict(status_counts),
        records=records,
    )


def _dedupe_jobs(jobs: list[JobListing]) -> tuple[list[JobListing], int]:
    seen_hashes: set[str] = set()
    unique_jobs: list[JobListing] = []
    duplicate_count = 0
    for job in jobs:
        if job.content_hash in seen_hashes:
            duplicate_count += 1
            continue
        seen_hashes.add(job.content_hash)
        unique_jobs.append(job)
    return unique_jobs, duplicate_count
