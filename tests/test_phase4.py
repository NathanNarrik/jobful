from __future__ import annotations

import unittest
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.deps import get_db
from api.main import app
from db.import_phase3 import import_result
from db.models import Base, Company, Job, UserApplication
from models import JobListing, JobNormalization, NormalizationResult, NormalizedJobRecord


def sample_record(**job_overrides: object) -> NormalizedJobRecord:
    values = {
        "company_name": "ExampleCo",
        "job_title": "Software Engineering Intern, Summer 2026",
        "job_url": "https://example.com/jobs/123",
        "ats_provider": "greenhouse",
        "ats_job_id": "123",
        "location": ["Remote", "New York, NY"],
        "raw_description": "Python and React internship for undergraduate students graduating in 2026.",
        "description_html": None,
        "employment_type": "Intern",
        "departments": ["Engineering"],
        "date_posted": None,
        "content_hash": "b" * 64,
        "extracted_at": datetime.now(UTC),
    }
    values.update(job_overrides)
    job = JobListing.model_validate(values)
    return NormalizedJobRecord(
        job=job,
        cleaned_description="Python and React internship for undergraduate students graduating in 2026.",
        normalization=JobNormalization(
            program_type="internship",
            academic_levels=["undergraduate"],
            degree_requirements=["computer science"],
            required_grad_years=[2026],
            visa_sponsorship=True,
            visa_status="sponsors",
            required_skills=["python", "react"],
            nice_to_have_skills=["docker"],
            min_gpa=3.2,
            clearance_required=False,
            remote_type="remote",
            normalization_status="COMPLETE",
            confidence=0.93,
            review_reasons=[],
        ),
        normalization_method="heuristic",
        normalized_at=datetime.now(UTC),
    )


def sample_result(records: list[NormalizedJobRecord] | None = None) -> NormalizationResult:
    records = records or [sample_record()]
    return NormalizationResult(
        generated_at=datetime.now(UTC),
        source_job_count=len(records),
        normalized_job_count=len(records),
        duplicate_job_count=0,
        status_counts={"COMPLETE": len(records)},
        records=records,
    )


class Phase4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False, future=True)

        def override_db():
            with self.Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_model_creation_imports_phase3_records(self) -> None:
        with Session(self.engine) as session:
            summary = import_result(session, sample_result())

            self.assertEqual(summary.records_read, 1)
            self.assertEqual(summary.companies_inserted, 1)
            self.assertEqual(summary.jobs_inserted, 1)
            self.assertEqual(session.scalar(select(Company).where(Company.name == "ExampleCo")).ats_provider, "greenhouse")
            self.assertEqual(session.scalar(select(Job).where(Job.content_hash == "b" * 64)).required_skills, ["python", "react"])

    def test_import_upserts_by_content_hash_and_company(self) -> None:
        first = sample_result()
        second = sample_result([sample_record(job_title="Updated Internship")])

        with Session(self.engine) as session:
            first_summary = import_result(session, first)
            second_summary = import_result(session, second)

            self.assertEqual(first_summary.jobs_inserted, 1)
            self.assertEqual(second_summary.jobs_updated, 1)
            self.assertEqual(session.scalar(select(Job).where(Job.content_hash == "b" * 64)).job_title, "Updated Internship")
            self.assertEqual(session.scalar(select(Company).where(Company.name == "ExampleCo")).name, "ExampleCo")

    def test_health_and_jobs_filters(self) -> None:
        with Session(self.engine) as session:
            import_result(session, sample_result())

        self.assertEqual(self.client.get("/health").json(), {"status": "ok", "database": "ok"})
        jobs = self.client.get(
            "/jobs?skill=python&grad_year=2026&academic_level=undergraduate&company=example"
        ).json()

        self.assertEqual(jobs["total"], 1)
        self.assertEqual(jobs["items"][0]["company_name"], "ExampleCo")

    def test_jobs_support_location_company_and_seen_date_filters(self) -> None:
        with Session(self.engine) as session:
            import_result(session, sample_result())
            seen_at = session.scalar(select(Job.last_seen_at)).isoformat()

        jobs = self.client.get(
            f"/jobs?location=Remote&company=ExampleCo&seen_before={seen_at}"
        ).json()

        self.assertEqual(jobs["total"], 1)
        self.assertEqual(jobs["items"][0]["job_title"], "Software Engineering Intern, Summer 2026")

    def test_job_detail_companies_stats_and_skills(self) -> None:
        with Session(self.engine) as session:
            import_result(session, sample_result())
            job_id = str(session.scalar(select(Job.id)))
            company_id = str(session.scalar(select(Company.id)))

        self.assertEqual(self.client.get(f"/jobs/{job_id}").json()["required_skills"], ["python", "react"])
        self.assertEqual(self.client.get("/companies").json()[0]["active_job_count"], 1)
        self.assertEqual(len(self.client.get(f"/companies/{company_id}/jobs").json()), 1)
        self.assertEqual(self.client.get("/stats").json()["active_jobs"], 1)
        self.assertEqual(self.client.get("/skills/popular").json()[0], {"skill": "python", "count": 1})

    def test_application_pipeline_create_update_and_list(self) -> None:
        with Session(self.engine) as session:
            import_result(session, sample_result())
            job_id = str(session.scalar(select(Job.id)))

        created = self.client.post(
            "/applications",
            json={"job_id": job_id, "status": "SAVED"},
        ).json()
        self.assertEqual(created["status"], "SAVED")
        self.assertEqual(created["job"]["company_name"], "ExampleCo")

        updated = self.client.patch(
            f"/applications/{created['id']}",
            json={"status": "APPLIED", "notes": "Submitted on the company site", "kanban_order": 2},
        ).json()
        self.assertEqual(updated["status"], "APPLIED")
        self.assertEqual(updated["notes"], "Submitted on the company site")

        pipeline = self.client.get("/applications").json()
        self.assertEqual(len(pipeline), 1)
        self.assertEqual(pipeline[0]["status"], "APPLIED")
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(UserApplication.status)), "APPLIED")


if __name__ == "__main__":
    unittest.main()
