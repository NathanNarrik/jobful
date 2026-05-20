from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0001_events_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_name", sa.Text(), nullable=False),
        sa.Column("firm_kind", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_type", sa.String(length=120)),
        sa.Column("last_error_message", sa.Text()),
        sa.UniqueConstraint("source_url", name="uq_event_sources_source_url"),
    )
    op.create_index("ix_event_sources_firm_name", "event_sources", ["firm_name"])
    op.create_index("ix_event_sources_firm_kind", "event_sources", ["firm_kind"])
    op.create_index("ix_event_sources_is_active", "event_sources", ["is_active"])

    op.create_table(
        "recruiting_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("event_sources.id", ondelete="SET NULL")),
        sa.Column("firm_name", sa.Text(), nullable=False),
        sa.Column("firm_kind", sa.String(length=64), nullable=False),
        sa.Column("event_title", sa.Text(), nullable=False),
        sa.Column("event_url", sa.Text(), nullable=False),
        sa.Column("registration_url", sa.Text()),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.Text()),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("audience_tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("location", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("location_type", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("timezone", sa.String(length=64)),
        sa.Column("description", sa.Text()),
        sa.Column("raw_payload", sa.JSON()),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("content_hash", name="uq_recruiting_events_content_hash"),
    )
    for name, columns in {
        "ix_recruiting_events_source_id": ["source_id"],
        "ix_recruiting_events_firm_name": ["firm_name"],
        "ix_recruiting_events_firm_kind": ["firm_kind"],
        "ix_recruiting_events_event_type": ["event_type"],
        "ix_recruiting_events_location_type": ["location_type"],
        "ix_recruiting_events_starts_at": ["starts_at"],
        "ix_recruiting_events_last_seen_at": ["last_seen_at"],
        "ix_recruiting_events_is_active": ["is_active"],
    }.items():
        op.create_index(name, "recruiting_events", columns)
    op.create_index("ix_recruiting_events_audience_tags_gin", "recruiting_events", ["audience_tags"], postgresql_using="gin")
    op.create_index("ix_recruiting_events_location_gin", "recruiting_events", ["location"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_table("recruiting_events")
    op.drop_table("event_sources")
