from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0002_user_applications"
down_revision = "0001_phase4_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("kanban_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_applications_user_job"),
    )
    op.create_index("ix_user_applications_user_id", "user_applications", ["user_id"])
    op.create_index("ix_user_applications_job_id", "user_applications", ["job_id"])
    op.create_index("ix_user_applications_status", "user_applications", ["status"])
    op.create_index(
        "ix_user_applications_user_status_order",
        "user_applications",
        ["user_id", "status", "kanban_order"],
    )


def downgrade() -> None:
    op.drop_table("user_applications")
