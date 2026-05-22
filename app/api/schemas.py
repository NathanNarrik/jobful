from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    company_name: str
    job_title: str
    job_url: str
    location: list[str]
    program_type: str
    academic_levels: list[str]
    required_grad_years: list[int]
    visa_status: str
    remote_type: str
    required_skills: list[str]
    normalization_status: str
    normalization_confidence: float
    date_posted: datetime | None
    last_seen_at: datetime


class JobDetail(JobListItem):
    ats_provider: str
    ats_job_id: str
    departments: list[str]
    employment_type: str | None
    degree_requirements: list[str]
    visa_sponsorship: bool | None
    nice_to_have_skills: list[str]
    min_gpa: float | None
    clearance_required: bool
    cleaned_description: str | None
    raw_description: str | None
    description_html: str | None
    normalization_method: str
    normalization_review_reasons: list[str]
    normalized_at: datetime
    first_seen_at: datetime
    is_active: bool


class PaginatedJobsResponse(BaseModel):
    items: list[JobListItem]
    total: int
    limit: int
    offset: int


class EventListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    firm_name: str
    firm_kind: str
    event_title: str
    event_url: str
    registration_url: str | None
    event_type: str
    audience_tags: list[str]
    location: list[str]
    location_type: str
    starts_at: datetime
    ends_at: datetime | None
    timezone: str | None
    last_seen_at: datetime
    is_active: bool


class EventDetail(EventListItem):
    source_id: UUID | None
    source_provider: str
    source_event_id: str | None
    description: str | None
    raw_payload: dict[str, Any] | None
    first_seen_at: datetime
    is_active: bool


class PaginatedEventsResponse(BaseModel):
    items: list[EventListItem]
    total: int
    limit: int
    offset: int


class EventSourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    firm_name: str
    firm_kind: str
    source_url: str
    source_provider: str
    source_scope: str = "company_page"
    source_status: str = "productive"
    is_active: bool
    last_scraped_at: datetime | None
    last_success_at: datetime | None
    last_error_type: str | None
    last_error_message: str | None
    event_count: int = 0
    active_event_count: int = 0


class CompanySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    ats_provider: str
    career_page_url: str | None
    ats_board_token: str | None
    is_active: bool
    last_scraped_at: datetime | None
    job_count: int = 0
    active_job_count: int = 0


class SkillCount(BaseModel):
    skill: str
    count: int


class StatsSummary(BaseModel):
    total_jobs: int
    active_jobs: int
    total_companies: int
    last_updated: datetime | None
    jobs_by_program_type: dict[str, int]
    jobs_by_remote_type: dict[str, int]
    jobs_by_visa_status: dict[str, int]
    needs_review_count: int


class HealthResponse(BaseModel):
    status: str
    database: str
    events_database: str = "not_configured"


ApplicationStatus = Literal[
    "SAVED",
    "APPLIED",
    "PHONE_SCREEN",
    "TECHNICAL",
    "FINAL",
    "OFFER",
    "REJECTED",
]


class ApplicationCreate(BaseModel):
    job_id: UUID
    status: ApplicationStatus = "SAVED"


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = None
    kanban_order: int | None = None
    applied_at: datetime | None = None


class ApplicationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    job_id: UUID | None
    status: ApplicationStatus
    applied_at: datetime | None
    notes: str | None
    kanban_order: int
    created_at: datetime
    updated_at: datetime
    job: JobListItem | None = None


def model_to_schema_dict(model: Any) -> dict[str, Any]:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}
