from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Integer, String, Text, cast, func, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import JobDetail, JobListItem, PaginatedJobsResponse
from db.models import Job


router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=PaginatedJobsResponse)
def list_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    program_type: str | None = None,
    remote_type: str | None = None,
    visa_status: str | None = None,
    grad_year: int | None = None,
    academic_level: str | None = None,
    skill: str | None = None,
    location: str | None = None,
    company_id: UUID | None = None,
    company: str | None = None,
    normalization_status: str | None = None,
    posted_after: datetime | None = None,
    posted_before: datetime | None = None,
    seen_after: datetime | None = None,
    seen_before: datetime | None = None,
    search: str | None = None,
    active_only: bool = True,
) -> PaginatedJobsResponse:
    stmt = select(Job)
    count_stmt = select(func.count()).select_from(Job)
    filters = build_filters(
        db,
        program_type=program_type,
        remote_type=remote_type,
        visa_status=visa_status,
        grad_year=grad_year,
        academic_level=academic_level,
        skill=skill,
        location=location,
        company_id=company_id,
        company=company,
        normalization_status=normalization_status,
        posted_after=posted_after,
        posted_before=posted_before,
        seen_after=seen_after,
        seen_before=seen_before,
        search=search,
        active_only=active_only,
    )
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int(db.execute(count_stmt).scalar_one())
    jobs = db.execute(
        stmt.order_by(Job.last_seen_at.desc(), Job.id.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return PaginatedJobsResponse(
        items=[JobListItem.model_validate(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: UUID, db: Session = Depends(get_db)) -> JobDetail:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDetail.model_validate(job)


def build_filters(
    db: Session,
    *,
    program_type: str | None,
    remote_type: str | None,
    visa_status: str | None,
    grad_year: int | None,
    academic_level: str | None,
    skill: str | None,
    location: str | None,
    company_id: UUID | None,
    company: str | None,
    normalization_status: str | None,
    posted_after: datetime | None,
    posted_before: datetime | None,
    seen_after: datetime | None,
    seen_before: datetime | None,
    search: str | None,
    active_only: bool,
) -> list[object]:
    filters: list[object] = []
    if active_only:
        filters.append(Job.is_active.is_(True))
    if program_type:
        filters.append(Job.program_type == program_type)
    if remote_type:
        filters.append(Job.remote_type == remote_type)
    if visa_status:
        filters.append(Job.visa_status == visa_status)
    if company_id:
        filters.append(Job.company_id == company_id)
    if company:
        filters.append(Job.company_name.ilike(f"%{company.strip()}%"))
    if normalization_status:
        filters.append(Job.normalization_status == normalization_status)
    if posted_after:
        filters.append(Job.date_posted >= posted_after)
    if posted_before:
        filters.append(Job.date_posted <= posted_before)
    if seen_after:
        filters.append(Job.last_seen_at >= seen_after)
    if seen_before:
        filters.append(Job.last_seen_at <= seen_before)
    if grad_year is not None:
        filters.append(array_contains(db, Job.required_grad_years, grad_year))
    if academic_level:
        filters.append(array_contains(db, Job.academic_levels, academic_level))
    if skill:
        normalized_skill = skill.strip().lower()
        filters.append(array_contains(db, Job.required_skills, normalized_skill))
    if location:
        filters.append(array_contains(db, Job.location, location))
    if search:
        token = f"%{search.strip()}%"
        filters.append(or_(Job.job_title.ilike(token), Job.company_name.ilike(token)))
    return filters


def array_contains(db: Session, column: object, value: object) -> object:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        array_type = postgresql.ARRAY(Integer()) if isinstance(value, int) else postgresql.ARRAY(Text())
        return column.op("@>")(cast(postgresql.array([value]), array_type))
    token = f'"{value}"' if isinstance(value, str) else str(value)
    return cast(column, String).ilike(f"%{token}%")
