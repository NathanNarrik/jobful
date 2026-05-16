from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, CHAR, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class PortableStringList(TypeDecorator[list[str]]):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.ARRAY(Text()))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> list[str]:
        if value is None:
            return []
        return [str(item) for item in value if item is not None]

    def process_result_value(self, value: Any, dialect: Any) -> list[str]:
        return list(value or [])


class PortableIntegerList(TypeDecorator[list[int]]):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.ARRAY(Integer()))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> list[int]:
        if value is None:
            return []
        return [int(item) for item in value if item is not None]

    def process_result_value(self, value: Any, dialect: Any) -> list[int]:
        return [int(item) for item in value or []]


class PortableUUID(TypeDecorator[uuid.UUID]):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> str | uuid.UUID | None:
        if value is None:
            return None
        parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return parsed if dialect.name == "postgresql" else str(parsed)

    def process_result_value(self, value: Any, dialect: Any) -> uuid.UUID | None:
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("name", "ats_provider", name="uq_companies_name_ats_provider"),
        Index("ix_companies_ats_provider", "ats_provider"),
        Index("ix_companies_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    career_page_url: Mapped[str | None] = mapped_column(Text)
    ats_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    ats_board_token: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_jobs_content_hash"),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_ats_provider", "ats_provider"),
        Index("ix_jobs_program_type", "program_type"),
        Index("ix_jobs_remote_type", "remote_type"),
        Index("ix_jobs_visa_status", "visa_status"),
        Index("ix_jobs_normalization_status", "normalization_status"),
        Index("ix_jobs_last_seen_at", "last_seen_at"),
        Index("ix_jobs_is_active", "is_active"),
        Index("ix_jobs_location_gin", "location", postgresql_using="gin"),
        Index("ix_jobs_required_skills_gin", "required_skills", postgresql_using="gin"),
        Index("ix_jobs_grad_years_gin", "required_grad_years", postgresql_using="gin"),
        Index("ix_jobs_academic_levels_gin", "academic_levels", postgresql_using="gin"),
        Index("ix_jobs_degree_requirements_gin", "degree_requirements", postgresql_using="gin"),
        Index(
            "ix_jobs_complete_last_seen",
            "last_seen_at",
            postgresql_where=text("normalization_status = 'COMPLETE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(PortableUUID, ForeignKey("companies.id"), nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    job_title: Mapped[str] = mapped_column(Text, nullable=False)
    job_url: Mapped[str] = mapped_column(Text, nullable=False)
    ats_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    ats_job_id: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    raw_description: Mapped[str | None] = mapped_column(Text)
    cleaned_description: Mapped[str | None] = mapped_column(Text)
    description_html: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(Text)
    departments: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    date_posted: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    program_type: Mapped[str] = mapped_column(String(32), nullable=False)
    academic_levels: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    degree_requirements: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    required_grad_years: Mapped[list[int]] = mapped_column(PortableIntegerList, nullable=False, default=list)
    visa_sponsorship: Mapped[bool | None] = mapped_column(Boolean)
    visa_status: Mapped[str] = mapped_column(String(64), nullable=False)
    required_skills: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    nice_to_have_skills: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    min_gpa: Mapped[float | None] = mapped_column(Numeric(3, 2))
    clearance_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_type: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_status: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_method: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    normalization_review_reasons: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    normalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    company: Mapped[Company] = relationship(back_populates="jobs")
