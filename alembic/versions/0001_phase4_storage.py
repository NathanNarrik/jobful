from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0001_phase4_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("career_page_url", sa.Text()),
        sa.Column("ats_provider", sa.String(length=32), nullable=False),
        sa.Column("ats_board_token", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("name", "ats_provider", name="uq_companies_name_ats_provider"),
    )
    op.create_index("ix_companies_ats_provider", "companies", ["ats_provider"])
    op.create_index("ix_companies_is_active", "companies", ["is_active"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("job_title", sa.Text(), nullable=False),
        sa.Column("job_url", sa.Text(), nullable=False),
        sa.Column("ats_provider", sa.String(length=32), nullable=False),
        sa.Column("ats_job_id", sa.Text(), nullable=False),
        sa.Column("location", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("raw_description", sa.Text()),
        sa.Column("cleaned_description", sa.Text()),
        sa.Column("description_html", sa.Text()),
        sa.Column("employment_type", sa.Text()),
        sa.Column("departments", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("date_posted", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("program_type", sa.String(length=32), nullable=False),
        sa.Column("academic_levels", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("degree_requirements", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("required_grad_years", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("visa_sponsorship", sa.Boolean()),
        sa.Column("visa_status", sa.String(length=64), nullable=False),
        sa.Column("required_skills", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("nice_to_have_skills", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("min_gpa", sa.Numeric(3, 2)),
        sa.Column("clearance_required", sa.Boolean(), nullable=False),
        sa.Column("remote_type", sa.String(length=32), nullable=False),
        sa.Column("normalization_status", sa.String(length=32), nullable=False),
        sa.Column("normalization_method", sa.String(length=32), nullable=False),
        sa.Column("normalization_confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("normalization_review_reasons", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("content_hash", name="uq_jobs_content_hash"),
    )
    for name, columns in {
        "ix_jobs_company_id": ["company_id"],
        "ix_jobs_ats_provider": ["ats_provider"],
        "ix_jobs_program_type": ["program_type"],
        "ix_jobs_remote_type": ["remote_type"],
        "ix_jobs_visa_status": ["visa_status"],
        "ix_jobs_normalization_status": ["normalization_status"],
        "ix_jobs_last_seen_at": ["last_seen_at"],
        "ix_jobs_is_active": ["is_active"],
    }.items():
        op.create_index(name, "jobs", columns)
    for name, columns in {
        "ix_jobs_location_gin": ["location"],
        "ix_jobs_required_skills_gin": ["required_skills"],
        "ix_jobs_grad_years_gin": ["required_grad_years"],
        "ix_jobs_academic_levels_gin": ["academic_levels"],
        "ix_jobs_degree_requirements_gin": ["degree_requirements"],
    }.items():
        op.create_index(name, "jobs", columns, postgresql_using="gin")
    op.create_index(
        "ix_jobs_complete_last_seen",
        "jobs",
        ["last_seen_at"],
        postgresql_where=sa.text("normalization_status = 'COMPLETE'"),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("companies")
