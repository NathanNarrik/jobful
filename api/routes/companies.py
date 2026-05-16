from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import CompanySummary, JobListItem
from db.models import Company, Job


router = APIRouter(tags=["companies"])


@router.get("/companies", response_model=list[CompanySummary])
def list_companies(db: Session = Depends(get_db)) -> list[CompanySummary]:
    rows = db.execute(
        select(
            Company,
            func.count(Job.id).label("job_count"),
            func.count(Job.id).filter(Job.is_active.is_(True)).label("active_job_count"),
        )
        .outerjoin(Job)
        .group_by(Company.id)
        .order_by(Company.name.asc())
    ).all()
    return [
        CompanySummary.model_validate(company).model_copy(
            update={
                "job_count": int(job_count),
                "active_job_count": int(active_job_count),
            }
        )
        for company, job_count, active_job_count in rows
    ]


@router.get("/companies/{company_id}/jobs", response_model=list[JobListItem])
def list_company_jobs(company_id: UUID, db: Session = Depends(get_db)) -> list[JobListItem]:
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    jobs = db.execute(
        select(Job)
        .where(Job.company_id == company_id, Job.is_active.is_(True))
        .order_by(Job.last_seen_at.desc(), Job.id.desc())
        .limit(100)
    ).scalars().all()
    return [JobListItem.model_validate(job) for job in jobs]
