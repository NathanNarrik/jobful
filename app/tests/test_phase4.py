from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_events_db
from app.api.main import app
from app.db.import_phase3 import import_result
from app.db.models import Base, Company, Job, UserApplication
from app.events.db.models import EventBase
from app.models import JobListing, JobNormalization, NormalizationResult, NormalizedJobRecord
from app.notifications.job_alerts import send_new_job_alerts, should_alert_for_record


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
        self.email_alert_env = patch.dict(os.environ, {"JOBFUL_EMAIL_ALERTS_ENABLED": "false"}, clear=False)
        self.email_alert_env.start()
        self.engine = create_engine(
            "sqlite+pysqlite://",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        EventBase.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False, future=True)

        def override_db():
            with self.Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_events_db] = override_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.email_alert_env.stop()
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

    def test_import_alerts_for_new_jobs_only_once(self) -> None:
        apple = sample_record(company_name="Apple", content_hash="a" * 64)

        with Session(self.engine) as session:
            with patch("app.db.import_phase3.send_new_job_alerts") as alerts:
                first_summary = import_result(session, sample_result([apple]))
                second_summary = import_result(session, sample_result([apple]))

        self.assertEqual(first_summary.jobs_inserted, 1)
        self.assertEqual(second_summary.jobs_updated, 1)
        self.assertEqual(alerts.call_count, 1)
        self.assertEqual(alerts.call_args.args[0][0].job.company_name, "Apple")

    def test_import_passes_all_inserted_records_to_alert_filter(self) -> None:
        microsoft_full_time = sample_record(
            company_name="Microsoft",
            job_title="Software Engineer",
            employment_type="Full-time",
            content_hash="m" * 64,
        )
        microsoft_full_time.normalization.program_type = "experienced"
        example_intern = sample_record(company_name="ExampleCo", content_hash="e" * 64)

        with Session(self.engine) as session:
            with patch("app.db.import_phase3.send_new_job_alerts") as alerts:
                import_result(session, sample_result([microsoft_full_time, example_intern]))

        alerts.assert_called_once()
        self.assertEqual(alerts.call_args.args[0], [microsoft_full_time, example_intern])

    def test_new_job_alert_filter_matches_recent_cs_jobs_only(self) -> None:
        recent_cs = sample_record(company_name="Apple", date_posted=datetime.now(UTC))
        old_cs = sample_record(
            company_name="Google",
            date_posted=datetime.now(UTC) - timedelta(days=7),
            content_hash="o" * 64,
        )
        unknown_posted = sample_record(company_name="Meta", date_posted=None, content_hash="u" * 64)
        non_cs = sample_record(
            company_name="Datadog",
            job_title="Account Executive",
            employment_type="Full-time",
            raw_description="Own enterprise sales and customer relationships.",
            departments=["Sales"],
            content_hash="d" * 64,
            date_posted=datetime.now(UTC),
        )
        non_cs.cleaned_description = "Own enterprise sales and customer relationships."
        non_cs.normalization.program_type = "experienced"
        non_cs.normalization.required_skills = []
        non_cs.normalization.nice_to_have_skills = []

        self.assertTrue(should_alert_for_record(recent_cs))
        self.assertFalse(should_alert_for_record(old_cs))
        self.assertFalse(should_alert_for_record(unknown_posted))
        self.assertFalse(should_alert_for_record(non_cs))

    def test_new_job_alerts_send_one_email_for_batch(self) -> None:
        first = sample_record(company_name="Google", content_hash="1" * 64, date_posted=datetime.now(UTC))
        second = sample_record(company_name="Microsoft", content_hash="2" * 64, date_posted=datetime.now(UTC))

        with (
            patch.dict(os.environ, {"JOBFUL_EMAIL_ALERTS_ENABLED": "true"}, clear=False),
            patch("app.notifications.job_alerts.EmailConfig.from_env") as config_factory,
            patch("app.notifications.job_alerts.send_email") as send_email,
        ):
            config = config_factory.return_value
            config.is_configured = True
            summary = send_new_job_alerts([first, second])

        self.assertEqual(summary.sent, 2)
        send_email.assert_called_once()
        self.assertIn("2 new CS jobs", send_email.call_args.args[0])

    def test_import_marks_non_cs_jobs_inactive(self) -> None:
        non_cs = sample_record(
            job_title="Retail Sales Associate",
            raw_description="Help customers in store.",
            departments=["Stores"],
            content_hash="c" * 64,
        )
        non_cs.cleaned_description = "Help customers in store."
        non_cs.normalization.required_skills = []
        non_cs.normalization.nice_to_have_skills = []

        with Session(self.engine) as session:
            import_result(session, sample_result([non_cs]))

            job = session.scalar(select(Job).where(Job.content_hash == "c" * 64))
            self.assertFalse(job.is_active)

    def test_health_and_jobs_filters(self) -> None:
        with Session(self.engine) as session:
            import_result(session, sample_result())

        self.assertEqual(self.client.get("/health").json(), {"status": "ok", "database": "ok", "events_database": "ok"})
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

    def test_jobs_filter_grad_year_includes_unrestricted_student_roles_and_country(self) -> None:
        unrestricted = sample_record(
            content_hash="c" * 64,
            job_title="Software Engineering Intern, Summer 2027",
            location=["Toronto, Canada"],
            date_posted=datetime(2026, 5, 2, tzinfo=UTC),
        )
        unrestricted.normalization.required_grad_years = []
        unrestricted.normalization.program_type = "internship"

        with Session(self.engine) as session:
            import_result(session, sample_result([unrestricted]))

        jobs = self.client.get("/jobs?grad_year=2030&country=Canada").json()

        self.assertEqual(jobs["total"], 1)
        self.assertEqual(jobs["items"][0]["job_title"], "Software Engineering Intern, Summer 2027")

    def test_jobs_default_to_newest_posted_first(self) -> None:
        old = sample_record(
            content_hash="d" * 64,
            job_title="Older Software Engineering Internship",
            date_posted=datetime(2026, 1, 1, tzinfo=UTC),
        )
        recent = sample_record(
            content_hash="e" * 64,
            job_title="Newer Software Engineering Internship",
            date_posted=datetime(2026, 5, 1, tzinfo=UTC),
        )

        with Session(self.engine) as session:
            import_result(session, sample_result([old, recent]))

        jobs = self.client.get("/jobs?limit=2").json()

        self.assertEqual(jobs["items"][0]["job_title"], "Newer Software Engineering Internship")
        self.assertEqual(jobs["items"][1]["job_title"], "Older Software Engineering Internship")

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
