from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.engine import create_jobful_engine
from app.db.models import Job
from app.normalizers.relevance import is_cs_relevant_job


def filter_to_cs_jobs(session: Session, *, dry_run: bool = False, batch_size: int = 1000) -> dict[str, int]:
    active_before = int(session.execute(select(func.count()).select_from(Job).where(Job.is_active.is_(True))).scalar_one())
    checked = 0
    kept_active = 0
    marked_inactive = 0
    kept_company_ids: set[Any] = set()
    to_deactivate: list[Any] = []

    rows = session.execute(
        select(
            Job.id,
            Job.company_id,
            Job.job_title,
            Job.departments,
            Job.required_skills,
            Job.nice_to_have_skills,
            Job.cleaned_description,
            Job.raw_description,
        ).where(Job.is_active.is_(True))
    )
    for row in rows:
        checked += 1
        is_relevant = is_cs_relevant_job(
            title=row.job_title,
            departments=row.departments,
            required_skills=row.required_skills,
            nice_to_have_skills=row.nice_to_have_skills,
            description=row.cleaned_description or row.raw_description or "",
        )
        if is_relevant:
            kept_active += 1
            kept_company_ids.add(row.company_id)
        else:
            to_deactivate.append(row.id)

        if len(to_deactivate) >= batch_size and not dry_run:
            marked_inactive += len(to_deactivate)
            _deactivate(session, to_deactivate)
            to_deactivate.clear()

    if not dry_run and to_deactivate:
        marked_inactive += len(to_deactivate)
        _deactivate(session, to_deactivate)
        to_deactivate.clear()

    if not dry_run:
        session.commit()
        active_after = int(session.execute(select(func.count()).select_from(Job).where(Job.is_active.is_(True))).scalar_one())
    else:
        active_after = kept_active
        marked_inactive = active_before - kept_active

    return {
        "active_before": active_before,
        "checked": checked,
        "kept_active": kept_active,
        "marked_inactive": marked_inactive,
        "active_after": active_after,
        "active_companies_after": _active_company_count(session) if not dry_run else len(kept_company_ids),
    }


def _deactivate(session: Session, job_ids: list[Any]) -> None:
    session.execute(update(Job).where(Job.id.in_(job_ids)).values(is_active=False))


def _active_company_count(session: Session) -> int:
    return int(
        session.execute(
            select(func.count(func.distinct(Job.company_id))).where(Job.is_active.is_(True))
        ).scalar_one()
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mark non-CS jobs inactive while keeping CS/tech roles visible.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = create_jobful_engine(args.database_url)
    with Session(engine) as session:
        summary = filter_to_cs_jobs(session, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
