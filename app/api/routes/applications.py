from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.api.schemas import ApplicationCreate, ApplicationRecord, ApplicationUpdate
from app.db.models import Job, UserApplication, utc_now


router = APIRouter(tags=["applications"])

DEV_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
APPLICATION_STATUSES = {
    "SAVED",
    "APPLIED",
    "PHONE_SCREEN",
    "TECHNICAL",
    "FINAL",
    "OFFER",
    "REJECTED",
}


def current_user_id(x_jobful_user_id: str | None = Header(default=None)) -> UUID:
    if not x_jobful_user_id:
        return DEV_USER_ID
    try:
        return UUID(x_jobful_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid X-Jobful-User-Id header") from exc


@router.get("/applications", response_model=list[ApplicationRecord])
def list_applications(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(current_user_id),
) -> list[ApplicationRecord]:
    applications = db.execute(
        select(UserApplication)
        .options(joinedload(UserApplication.job))
        .where(UserApplication.user_id == user_id)
        .order_by(UserApplication.status.asc(), UserApplication.kanban_order.asc(), UserApplication.updated_at.desc())
    ).scalars().all()
    return [ApplicationRecord.model_validate(application) for application in applications]


@router.post("/applications", response_model=ApplicationRecord, status_code=201)
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(current_user_id),
) -> ApplicationRecord:
    job = db.get(Job, payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    existing = db.execute(
        select(UserApplication)
        .options(joinedload(UserApplication.job))
        .where(UserApplication.user_id == user_id, UserApplication.job_id == payload.job_id)
    ).scalar_one_or_none()
    if existing is not None:
        existing.status = payload.status
        existing.updated_at = utc_now()
        if payload.status == "APPLIED" and existing.applied_at is None:
            existing.applied_at = datetime.now(UTC)
        db.commit()
        db.refresh(existing)
        return ApplicationRecord.model_validate(existing)

    next_order = db.execute(
        select(func.coalesce(func.max(UserApplication.kanban_order), -1) + 1).where(
            UserApplication.user_id == user_id,
            UserApplication.status == payload.status,
        )
    ).scalar_one()
    application = UserApplication(
        user_id=user_id,
        job_id=payload.job_id,
        status=payload.status,
        kanban_order=int(next_order),
        applied_at=datetime.now(UTC) if payload.status == "APPLIED" else None,
    )
    db.add(application)
    db.commit()
    application = db.execute(
        select(UserApplication)
        .options(joinedload(UserApplication.job))
        .where(UserApplication.id == application.id)
    ).scalar_one()
    return ApplicationRecord.model_validate(application)


@router.patch("/applications/{application_id}", response_model=ApplicationRecord)
def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(current_user_id),
) -> ApplicationRecord:
    application = db.execute(
        select(UserApplication)
        .options(joinedload(UserApplication.job))
        .where(UserApplication.id == application_id, UserApplication.user_id == user_id)
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    if payload.status is not None:
        application.status = payload.status
        if payload.status == "APPLIED" and application.applied_at is None:
            application.applied_at = datetime.now(UTC)
    if payload.notes is not None:
        application.notes = payload.notes
    if payload.kanban_order is not None:
        application.kanban_order = payload.kanban_order
    if payload.applied_at is not None:
        application.applied_at = payload.applied_at
    application.updated_at = utc_now()
    db.commit()
    db.refresh(application)
    return ApplicationRecord.model_validate(application)
