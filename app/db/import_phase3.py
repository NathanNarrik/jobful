from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.engine import create_jobful_engine
from app.db.models import Base, Company, Job, utc_now
from app.models import NormalizationResult, NormalizedJobRecord
from app.normalizers.relevance import is_cs_relevant_job, is_cs_relevant_record


@dataclass(frozen=True)
class ImportSummary:
    records_read: int = 0
    companies_inserted: int = 0
    jobs_inserted: int = 0
    jobs_updated: int = 0
    skipped: int = 0
    failed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "records_read": self.records_read,
            "companies_inserted": self.companies_inserted,
            "jobs_inserted": self.jobs_inserted,
            "jobs_updated": self.jobs_updated,
            "skipped": self.skipped,
            "failed": self.failed,
        }


def load_normalization_result(path: Path) -> NormalizationResult:
    return NormalizationResult.model_validate_json(path.read_text(encoding="utf-8"))


def load_artifact_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def import_result(session: Session, result: NormalizationResult) -> ImportSummary:
    counters = {
        "records_read": len(result.records),
        "companies_inserted": 0,
        "jobs_inserted": 0,
        "jobs_updated": 0,
        "skipped": 0,
        "failed": 0,
    }

    for record in result.records:
        try:
            company, inserted_company = upsert_company(session, record)
            if inserted_company:
                counters["companies_inserted"] += 1
            inserted_job = upsert_job(session, record, company)
            if inserted_job:
                counters["jobs_inserted"] += 1
            else:
                counters["jobs_updated"] += 1
        except Exception:
            counters["failed"] += 1

    session.commit()
    return ImportSummary(**counters)


def upsert_company(session: Session, record: NormalizedJobRecord) -> tuple[Company, bool]:
    job = record.job
    existing = session.execute(
        select(Company).where(
            Company.name == job.company_name,
            Company.ats_provider == job.ats_provider,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.is_active = True
        existing.last_scraped_at = job.extracted_at
        return existing, False

    company = Company(
        name=job.company_name,
        ats_provider=job.ats_provider,
        is_active=True,
        last_scraped_at=job.extracted_at,
    )
    session.add(company)
    session.flush()
    return company, True


def upsert_job(session: Session, record: NormalizedJobRecord, company: Company) -> bool:
    existing = session.execute(
        select(Job).where(Job.content_hash == record.job.content_hash)
    ).scalar_one_or_none()
    values = job_values(record, company)

    if existing is not None:
        for key, value in values.items():
            if key not in {"id", "first_seen_at"}:
                setattr(existing, key, value)
        existing.last_seen_at = utc_now()
        existing.is_active = bool(values["is_active"])
        session.flush()
        return False

    session.add(Job(**values))
    session.flush()
    return True


def job_values(record: NormalizedJobRecord, company: Company) -> dict[str, Any]:
    job = record.job
    normalization = record.normalization
    now = utc_now()
    return {
        "company_id": company.id,
        "company_name": job.company_name,
        "job_title": job.job_title,
        "job_url": str(job.job_url),
        "ats_provider": job.ats_provider,
        "ats_job_id": job.ats_job_id,
        "location": job.location,
        "raw_description": job.raw_description,
        "cleaned_description": record.cleaned_description,
        "description_html": job.description_html,
        "employment_type": job.employment_type,
        "departments": job.departments,
        "date_posted": job.date_posted,
        "content_hash": job.content_hash,
        "extracted_at": job.extracted_at,
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": is_cs_relevant_normalized_record(record),
        "program_type": normalization.program_type,
        "academic_levels": normalization.academic_levels,
        "degree_requirements": normalization.degree_requirements,
        "required_grad_years": normalization.required_grad_years,
        "visa_sponsorship": normalization.visa_sponsorship,
        "visa_status": normalization.visa_status,
        "required_skills": normalization.required_skills,
        "nice_to_have_skills": normalization.nice_to_have_skills,
        "min_gpa": normalization.min_gpa,
        "clearance_required": normalization.clearance_required,
        "remote_type": normalization.remote_type,
        "normalization_status": normalization.normalization_status,
        "normalization_method": record.normalization_method,
        "normalization_confidence": normalization.confidence,
        "normalization_review_reasons": normalization.review_reasons,
        "normalized_at": record.normalized_at,
    }


def import_payload(session: Session, payload: dict[str, Any], *, batch_size: int = 1000) -> ImportSummary:
    records = payload.get("records") or []
    if not records:
        return ImportSummary()

    company_map, companies_inserted = upsert_companies_from_payload(session, records)
    values = [
        job_values_from_payload(record, company_map[company_key_from_payload(record)])
        for record in records
        if record.get("job", {}).get("content_hash")
    ]
    content_hashes = [value["content_hash"] for value in values]
    existing_hashes = fetch_existing_hashes(session, content_hashes)

    inserted = 0
    updated = 0
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        for batch in chunks(values, batch_size):
            stmt = pg_insert(Job).values(batch)
            update_values = {
                key: stmt.excluded[key]
                for key in batch[0]
                if key not in {"id", "content_hash", "first_seen_at"}
            }
            update_values["last_seen_at"] = utc_now()
            update_values["is_active"] = stmt.excluded["is_active"]
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[Job.content_hash],
                    set_=update_values,
                )
            )
    else:
        for value in values:
            existing = session.execute(select(Job).where(Job.content_hash == value["content_hash"])).scalar_one_or_none()
            if existing is None:
                session.add(Job(**value))
            else:
                for key, item in value.items():
                    if key not in {"id", "content_hash", "first_seen_at"}:
                        setattr(existing, key, item)
                existing.last_seen_at = utc_now()
                existing.is_active = bool(value["is_active"])

    session.commit()
    inserted = sum(1 for content_hash in content_hashes if content_hash not in existing_hashes)
    updated = len(content_hashes) - inserted
    return ImportSummary(
        records_read=len(records),
        companies_inserted=companies_inserted,
        jobs_inserted=inserted,
        jobs_updated=updated,
        skipped=len(records) - len(values),
        failed=0,
    )


def upsert_companies_from_payload(
    session: Session,
    records: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], Company], int]:
    keys = sorted({company_key_from_payload(record) for record in records})
    existing_companies = session.execute(
        select(Company).where(tuple_(Company.name, Company.ats_provider).in_(keys))
    ).scalars().all()
    company_map = {(company.name, company.ats_provider): company for company in existing_companies}
    inserted = 0

    for name, ats_provider in keys:
        if (name, ats_provider) in company_map:
            continue
        company = Company(name=name, ats_provider=ats_provider, is_active=True)
        session.add(company)
        company_map[(name, ats_provider)] = company
        inserted += 1

    session.flush()
    return company_map, inserted


def company_key_from_payload(record: dict[str, Any]) -> tuple[str, str]:
    job = record["job"]
    return str(job["company_name"]), str(job["ats_provider"])


def job_values_from_payload(record: dict[str, Any], company: Company) -> dict[str, Any]:
    job = record["job"]
    normalization = record["normalization"]
    now = utc_now()
    return {
        "id": uuid.uuid4(),
        "company_id": company.id,
        "company_name": job["company_name"],
        "job_title": job["job_title"],
        "job_url": job["job_url"],
        "ats_provider": job["ats_provider"],
        "ats_job_id": job["ats_job_id"],
        "location": job.get("location") or [],
        "raw_description": job.get("raw_description"),
        "cleaned_description": record.get("cleaned_description"),
        "description_html": job.get("description_html"),
        "employment_type": job.get("employment_type"),
        "departments": job.get("departments") or [],
        "date_posted": parse_datetime(job.get("date_posted")),
        "content_hash": job["content_hash"],
        "extracted_at": parse_datetime(job["extracted_at"]) or now,
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": is_cs_relevant_record(record),
        "program_type": normalization["program_type"],
        "academic_levels": normalization.get("academic_levels") or [],
        "degree_requirements": normalization.get("degree_requirements") or [],
        "required_grad_years": normalization.get("required_grad_years") or [],
        "visa_sponsorship": normalization.get("visa_sponsorship"),
        "visa_status": normalization["visa_status"],
        "required_skills": normalization.get("required_skills") or [],
        "nice_to_have_skills": normalization.get("nice_to_have_skills") or [],
        "min_gpa": normalization.get("min_gpa"),
        "clearance_required": bool(normalization.get("clearance_required", False)),
        "remote_type": normalization["remote_type"],
        "normalization_status": normalization["normalization_status"],
        "normalization_method": record["normalization_method"],
        "normalization_confidence": normalization.get("confidence", 0.5),
        "normalization_review_reasons": normalization.get("review_reasons") or [],
        "normalized_at": parse_datetime(record["normalized_at"]) or now,
    }


def parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def is_cs_relevant_normalized_record(record: NormalizedJobRecord) -> bool:
    return is_cs_relevant_job(
        title=record.job.job_title,
        departments=record.job.departments,
        required_skills=record.normalization.required_skills,
        nice_to_have_skills=record.normalization.nice_to_have_skills,
        description=record.cleaned_description or record.job.raw_description or "",
    )


def fetch_existing_hashes(session: Session, content_hashes: list[str], *, batch_size: int = 5000) -> set[str]:
    existing: set[str] = set()
    for batch in chunks(content_hashes, batch_size):
        existing.update(session.execute(select(Job.content_hash).where(Job.content_hash.in_(batch))).scalars())
    return existing


def chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def import_result_postgres(session: Session, result: NormalizationResult) -> ImportSummary:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return import_result(session, result)

    counters = {
        "records_read": len(result.records),
        "companies_inserted": 0,
        "jobs_inserted": 0,
        "jobs_updated": 0,
        "skipped": 0,
        "failed": 0,
    }
    for record in result.records:
        try:
            company, inserted_company = upsert_company(session, record)
            if inserted_company:
                counters["companies_inserted"] += 1
            values = job_values(record, company)
            existed = session.execute(
                select(Job.id).where(Job.content_hash == record.job.content_hash)
            ).scalar_one_or_none() is not None
            stmt = pg_insert(Job).values(**values)
            update_values = {
                key: stmt.excluded[key]
                for key in values
                if key not in {"id", "content_hash", "first_seen_at"}
            }
            update_values["last_seen_at"] = utc_now()
            update_values["is_active"] = stmt.excluded["is_active"]
            result_proxy = session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[Job.content_hash],
                    set_=update_values,
                )
            )
            if existed:
                counters["jobs_updated"] += int(result_proxy.rowcount or 0)
            elif result_proxy.rowcount == 1:
                counters["jobs_inserted"] += 1
        except Exception:
            counters["failed"] += 1
    session.commit()
    return ImportSummary(**counters)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a Phase 3 normalized Jobful artifact into the database.")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--create-tables", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = create_jobful_engine(args.database_url)
    if args.create_tables:
        Base.metadata.create_all(engine)
    payload = load_artifact_payload(args.artifact)
    with Session(engine) as session:
        summary = import_payload(session, payload)
    print(json.dumps(summary.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
