from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0002_event_source_health"
down_revision = "0001_events_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("event_sources", sa.Column("source_scope", sa.String(length=64), nullable=False, server_default="company_page"))
    op.add_column("event_sources", sa.Column("source_status", sa.String(length=64), nullable=False, server_default="productive"))
    op.alter_column("event_sources", "source_scope", server_default=None)
    op.alter_column("event_sources", "source_status", server_default=None)


def downgrade() -> None:
    op.drop_column("event_sources", "source_status")
    op.drop_column("event_sources", "source_scope")
