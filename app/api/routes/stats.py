from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import SkillCount, StatsSummary
from app.db.models import Company, Job


router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsSummary)
def get_stats(db: Session = Depends(get_db)) -> StatsSummary:
    total_jobs = int(db.execute(select(func.count()).select_from(Job)).scalar_one())
    active_jobs = int(db.execute(select(func.count()).select_from(Job).where(Job.is_active.is_(True))).scalar_one())
    total_companies = int(db.execute(select(func.count()).select_from(Company)).scalar_one())
    last_updated = db.execute(select(func.max(Job.last_seen_at))).scalar_one()

    return StatsSummary(
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        total_companies=total_companies,
        last_updated=last_updated,
        jobs_by_program_type=count_by(db, Job.program_type),
        jobs_by_remote_type=count_by(db, Job.remote_type),
        jobs_by_visa_status=count_by(db, Job.visa_status),
        needs_review_count=int(
            db.execute(
                select(func.count()).select_from(Job).where(Job.normalization_status == "NEEDS_REVIEW")
            ).scalar_one()
        ),
    )


@router.get("/skills/popular", response_model=list[SkillCount])
def popular_skills(limit: int = 25, db: Session = Depends(get_db)) -> list[SkillCount]:
    jobs = db.execute(select(Job.required_skills).where(Job.is_active.is_(True))).scalars().all()
    counter: Counter[str] = Counter()
    for skills in jobs:
        counter.update(skill for skill in skills if skill)
    return [SkillCount(skill=skill, count=count) for skill, count in counter.most_common(max(1, min(limit, 100)))]


def count_by(db: Session, column: object) -> dict[str, int]:
    rows = db.execute(
        select(column, func.count()).select_from(Job).where(Job.is_active.is_(True)).group_by(column)
    ).all()
    return {str(key): int(count) for key, count in rows if key is not None}
