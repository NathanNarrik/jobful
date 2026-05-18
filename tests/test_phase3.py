from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from models import JobListing, PullResult
from normalizers.cleaner import clean_description
from normalizers.ollama import normalize_with_ollama
from normalizers.pipeline import normalize_jobs
from normalizers.relevance import is_cs_relevant_job
from tasks import extract_and_normalize_source, normalize_jobs_task


def sample_job(**overrides: object) -> JobListing:
    values = {
        "company_name": "ExampleCo",
        "job_title": "Software Engineering Intern, Summer 2026",
        "job_url": "https://example.com/jobs/123",
        "ats_provider": "greenhouse",
        "ats_job_id": "123",
        "location": ["Remote"],
        "raw_description": (
            "<p>We are looking for a Python and React intern graduating in 2026. "
            "Undergraduate candidates preferred. Minimum GPA 3.2. "
            "Visa sponsorship is available. Nice to have: Docker. "
            "This is a remote role.</p>"
        ),
        "description_html": None,
        "employment_type": "Intern",
        "departments": ["Engineering"],
        "date_posted": None,
        "content_hash": "a" * 64,
        "extracted_at": datetime.now(UTC),
    }
    values.update(overrides)
    return JobListing.model_validate(values)


class Phase3Tests(unittest.TestCase):
    def test_clean_description_removes_html_and_boilerplate(self) -> None:
        cleaned = clean_description(
            "ignored",
            "<p>Hello&nbsp;world</p><p>We are an equal opportunity employer.</p>",
        )

        self.assertIn("Hello world", cleaned)
        self.assertNotIn("equal opportunity", cleaned.lower())

    def test_normalize_jobs_extracts_student_metadata(self) -> None:
        result = normalize_jobs([sample_job()], use_ollama=False)
        record = result.records[0]

        self.assertEqual(result.normalized_job_count, 1)
        self.assertEqual(record.normalization.program_type, "internship")
        self.assertIn("undergraduate", record.normalization.academic_levels)
        self.assertEqual(record.normalization.required_grad_years, [2026])
        self.assertEqual(record.normalization.visa_sponsorship, True)
        self.assertEqual(record.normalization.visa_status, "sponsors")
        self.assertEqual(record.normalization.remote_type, "remote")
        self.assertEqual(record.normalization.min_gpa, 3.2)
        self.assertGreater(record.normalization.confidence, 0.8)
        self.assertEqual(record.normalization.review_reasons, [])
        self.assertIn("python", record.normalization.required_skills)
        self.assertIn("react", record.normalization.required_skills)
        self.assertIn("docker", record.normalization.nice_to_have_skills)

    def test_normalize_jobs_extracts_academic_and_visa_edge_cases(self) -> None:
        job = sample_job(
            job_title="PhD Machine Learning Intern",
            raw_description=(
                "Candidates must be pursuing a PhD and graduate between 2026 and 2027. "
                "OPT/CPT candidates are welcome. This hybrid role requires Python."
            ),
            description_html=None,
            employment_type="Intern",
        )
        result = normalize_jobs([job], use_ollama=False)
        normalization = result.records[0].normalization

        self.assertEqual(normalization.program_type, "internship")
        self.assertIn("phd", normalization.academic_levels)
        self.assertIn("phd", normalization.degree_requirements)
        self.assertEqual(normalization.required_grad_years, [2026, 2027])
        self.assertEqual(normalization.visa_status, "opt_cpt_allowed")
        self.assertEqual(normalization.visa_sponsorship, True)
        self.assertEqual(normalization.remote_type, "hybrid")

    def test_normalize_jobs_dedupes_by_content_hash(self) -> None:
        result = normalize_jobs([sample_job(), sample_job()], use_ollama=False)

        self.assertEqual(result.source_job_count, 2)
        self.assertEqual(result.normalized_job_count, 1)
        self.assertEqual(result.duplicate_job_count, 1)

    def test_skill_matching_avoids_substring_false_positives(self) -> None:
        job = sample_job(
            job_title="Account Executive",
            raw_description="Build trust with internal customers and coordinate go-to-market planning.",
            description_html=None,
            employment_type=None,
        )
        result = normalize_jobs([job], use_ollama=False)

        self.assertNotIn("rust", result.records[0].normalization.required_skills)
        self.assertNotIn("go", result.records[0].normalization.required_skills)
        self.assertEqual(result.records[0].normalization.program_type, "other")

    def test_cs_relevance_filters_retail_but_keeps_technical_roles(self) -> None:
        self.assertTrue(
            is_cs_relevant_job(
                title="Software Engineer Intern",
                departments=["Engineering"],
                required_skills=["python"],
                description="Build backend services.",
            )
        )
        self.assertTrue(
            is_cs_relevant_job(
                title="Machine Learning Engineer",
                departments=["Data Science"],
                required_skills=[],
                description="Train production models.",
            )
        )
        self.assertTrue(
            is_cs_relevant_job(
                title="Solutions Architect",
                departments=["Cloud Engineering"],
                required_skills=["aws"],
                description="Design distributed systems for enterprise customers.",
            )
        )
        self.assertTrue(
            is_cs_relevant_job(
                title="Software Development Engineer in Test - Retail Engineering",
                departments=["Software and Services"],
                required_skills=[],
                description="Build automation for release quality.",
            )
        )
        self.assertTrue(
            is_cs_relevant_job(
                title="Data Analyst",
                departments=["Data Science"],
                required_skills=["sql"],
                description="Analyze product telemetry.",
            )
        )
        self.assertTrue(
            is_cs_relevant_job(
                title="Front-End Software Engineer",
                departments=["Software Engineering"],
                required_skills=["react"],
                description="Build product UI.",
            )
        )
        self.assertFalse(
            is_cs_relevant_job(
                title="Retail Sales Associate",
                departments=["Stores"],
                required_skills=[],
                description="Help customers in store.",
            )
        )
        self.assertFalse(
            is_cs_relevant_job(
                title="2nd Shift Quality Inspector",
                departments=["Engineering"],
                required_skills=[],
                description="Inspect manufacturing parts.",
            )
        )
        self.assertFalse(
            is_cs_relevant_job(
                title="Accountant, International",
                departments=["Finance"],
                required_skills=["sql"],
                description="Prepare journal entries and reconcile accounts.",
            )
        )
        self.assertFalse(
            is_cs_relevant_job(
                title="Customer Success Manager II, Retail",
                departments=["Customer Experience"],
                required_skills=[],
                description="Manage customer relationships.",
            )
        )
        self.assertFalse(
            is_cs_relevant_job(
                title="Front End Service Team Supervisor",
                departments=["Store Operations"],
                required_skills=[],
                description="Lead checkout associates.",
            )
        )

    def test_phase3_cli_writes_normalized_artifact(self) -> None:
        pull = PullResult(
            generated_at=datetime.now(UTC),
            source_count=1,
            successful_source_count=1,
            failed_source_count=0,
            job_count=1,
            sources=[],
            jobs=[sample_job()],
            failures=[],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "pull.json"
            output_path = Path(temp_dir) / "normalized.json"
            input_path.write_text(
                json.dumps(pull.model_dump(mode="json"), ensure_ascii=False),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "phase3.py",
                    str(input_path),
                    "-o",
                    str(output_path),
                    "--no-ollama",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertIn('"normalized_job_count": 1', completed.stdout)
        self.assertEqual(payload["normalized_job_count"], 1)
        self.assertEqual(payload["records"][0]["normalization"]["program_type"], "internship")

    def test_phase3_audit_cli_writes_csv_sample(self) -> None:
        result = normalize_jobs([sample_job()], use_ollama=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "normalized.json"
            output_path = Path(temp_dir) / "audit.csv"
            input_path.write_text(
                json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "phase3_audit.py",
                    str(input_path),
                    "-o",
                    str(output_path),
                    "--sample-size",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            csv_text = output_path.read_text(encoding="utf-8")

        self.assertIn('"sample_count": 1', completed.stdout)
        self.assertIn("human_notes", csv_text)
        self.assertIn("Software Engineering Intern", csv_text)

    def test_ollama_response_can_validate_new_schema(self) -> None:
        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "response": json.dumps(
                            {
                                "program_type": "internship",
                                "academic_levels": ["phd"],
                                "degree_requirements": ["phd"],
                                "required_grad_years": [2026],
                                "visa_sponsorship": True,
                                "visa_status": "opt_cpt_allowed",
                                "required_skills": ["python"],
                                "nice_to_have_skills": [],
                                "min_gpa": None,
                                "clearance_required": False,
                                "remote_type": "hybrid",
                                "confidence": 0.84,
                                "review_reasons": [],
                            }
                        )
                    }
                ).encode("utf-8")

        with (
            patch.dict(os.environ, {"JOBFUL_USE_OLLAMA": "true"}, clear=False),
            patch("normalizers.ollama.request.urlopen", return_value=FakeResponse()),
        ):
            normalization = normalize_with_ollama("PhD intern role. OPT/CPT welcome.")

        self.assertIsNotNone(normalization)
        assert normalization is not None
        self.assertEqual(normalization.program_type, "internship")
        self.assertEqual(normalization.visa_status, "opt_cpt_allowed")

    def test_celery_normalize_task_runs_without_broker_when_called_directly(self) -> None:
        result = normalize_jobs_task.run([sample_job().model_dump(mode="json")], use_ollama=False)

        self.assertEqual(result["normalized_job_count"], 1)
        self.assertEqual(result["records"][0]["normalization"]["program_type"], "internship")

    def test_celery_extract_and_normalize_task_uses_shared_pipeline(self) -> None:
        fake_extraction = {
            "source": {"source_url": "https://example.com/jobs", "status": "success", "job_count": 1},
            "jobs": [sample_job().model_dump(mode="json")],
            "failure": None,
        }

        with patch("tasks.extract_source.run", return_value=fake_extraction):
            result = extract_and_normalize_source.run("https://example.com/jobs", use_ollama=False)

        self.assertIsNone(result["failure"])
        self.assertEqual(result["normalization"]["normalized_job_count"], 1)


if __name__ == "__main__":
    unittest.main()
