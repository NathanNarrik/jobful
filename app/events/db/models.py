from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.models import PortableStringList, PortableUUID, utc_now


class EventBase(DeclarativeBase):
    pass


class EventSource(EventBase):
    __tablename__ = "event_sources"
    __table_args__ = (
        UniqueConstraint("source_url", name="uq_event_sources_source_url"),
        Index("ix_event_sources_firm_name", "firm_name"),
        Index("ix_event_sources_firm_kind", "firm_kind"),
        Index("ix_event_sources_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID, primary_key=True, default=uuid.uuid4)
    firm_name: Mapped[str] = mapped_column(Text, nullable=False)
    firm_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="company_events")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_type: Mapped[str | None] = mapped_column(String(120))
    last_error_message: Mapped[str | None] = mapped_column(Text)

    events: Mapped[list["RecruitingEvent"]] = relationship(back_populates="source")


class RecruitingEvent(EventBase):
    __tablename__ = "recruiting_events"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_recruiting_events_content_hash"),
        Index("ix_recruiting_events_source_id", "source_id"),
        Index("ix_recruiting_events_firm_name", "firm_name"),
        Index("ix_recruiting_events_firm_kind", "firm_kind"),
        Index("ix_recruiting_events_event_type", "event_type"),
        Index("ix_recruiting_events_location_type", "location_type"),
        Index("ix_recruiting_events_starts_at", "starts_at"),
        Index("ix_recruiting_events_last_seen_at", "last_seen_at"),
        Index("ix_recruiting_events_is_active", "is_active"),
        Index("ix_recruiting_events_audience_tags_gin", "audience_tags", postgresql_using="gin"),
        Index("ix_recruiting_events_location_gin", "location", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID | None] = mapped_column(PortableUUID, ForeignKey("event_sources.id", ondelete="SET NULL"))
    firm_name: Mapped[str] = mapped_column(Text, nullable=False)
    firm_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    event_title: Mapped[str] = mapped_column(Text, nullable=False)
    event_url: Mapped[str] = mapped_column(Text, nullable=False)
    registration_url: Mapped[str | None] = mapped_column(Text)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    audience_tags: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    location: Mapped[list[str]] = mapped_column(PortableStringList, nullable=False, default=list)
    location_type: Mapped[str] = mapped_column(String(32), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    source: Mapped[EventSource | None] = relationship(back_populates="events")
