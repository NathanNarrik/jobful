from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from extractors.amazon import AmazonExtractor
from extractors.google import GoogleExtractor
from extractors.talentbrew import TalentBrewExtractor
from extractors.workday import WorkdayExtractor
from proxy import ProxyPool
from queueing import QueueName, choose_queue, get_backoff_delay
from router import AtsRouter
from sources import DEFAULT_CAREER_URLS
from tasks import record_dead_letter


class Phase2Tests(unittest.TestCase):
    def test_choose_queue_classifies_priority_sources(self) -> None:
        self.assertEqual(choose_queue("https://www.amazon.jobs/en/").queue, QueueName.HIGH)
        self.assertEqual(choose_queue("https://jobs.lever.co/palantir").queue, QueueName.HIGH)
        self.assertEqual(
            choose_queue("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite").queue,
            QueueName.HIGH,
        )
        self.assertEqual(choose_queue("https://jobs.ashbyhq.com/ashby").queue, QueueName.SLOW)
        self.assertEqual(choose_queue("https://boards.greenhouse.io/airbnb").queue, QueueName.STANDARD)

    def test_default_sources_include_requested_top_company_expansion(self) -> None:
        self.assertGreaterEqual(len(DEFAULT_CAREER_URLS), 150)

        requested_sources = {
            "https://www.google.com/about/careers/applications/jobs/results",
            "https://www.amazon.jobs/en/search",
            "https://jobs.apple.com/en-us/search?sort=relevance",
            "https://www.metacareers.com/jobsearch",
            "https://explore.jobs.netflix.net/careers",
            "https://apply.careers.microsoft.com/careers",
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
            "https://jobs.lever.co/palantir",
            "https://jobs.ashbyhq.com/openai",
            "https://jobs.ashbyhq.com/cohere",
            "https://jobs.ashbyhq.com/cursor",
            "https://jobs.ashbyhq.com/snowflake",
            "https://jobs.smartrecruiters.com/ServiceNow",
            "https://jobs.sap.com/search/",
            "https://careers.arm.com/search-jobs",
            "https://jobs.intuit.com/search-jobs",
            "https://careers.qualcomm.com/careers/search",
            "https://careers.ti.com/en/sites/CX/jobs",
            "https://paloaltonetworks.wd5.myworkdayjobs.com/panwexternalcareers",
            "https://boards.greenhouse.io/deepmind",
            "https://boards.greenhouse.io/waymo",
            "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site",
        }

        self.assertTrue(requested_sources.issubset(DEFAULT_CAREER_URLS))
        self.assertEqual(len(DEFAULT_CAREER_URLS), len(set(DEFAULT_CAREER_URLS)))

    def test_backoff_increases_with_jitter(self) -> None:
        delay = get_backoff_delay(3, base=2.0, cap=300.0)
        self.assertGreaterEqual(delay, 8.0)
        self.assertLessEqual(delay, 8.8)

    def test_detect_only_returns_route_without_extracting(self) -> None:
        router = AtsRouter()

        self.assertEqual(router.detect_only("https://boards.greenhouse.io/airbnb").provider, "greenhouse")
        self.assertEqual(router.detect_only("https://jobs.lever.co/Flex").provider, "lever")
        self.assertEqual(router.detect_only("https://jobs.ashbyhq.com/ashby").provider, "ashby")
        self.assertEqual(router.detect_only("https://explore.jobs.netflix.net/careers").provider, "eightfold")
        self.assertEqual(router.detect_only("https://www.metacareers.com/jobsearch").provider, "meta")
        self.assertEqual(router.detect_only("https://jobs.smartrecruiters.com/ServiceNow").provider, "smartrecruiters")
        self.assertEqual(router.detect_only("https://jobs.sap.com/search/").provider, "successfactors")
        self.assertEqual(router.detect_only("https://apply.careers.microsoft.com/careers").provider, "eightfold")
        self.assertEqual(router.detect_only("https://careers.qualcomm.com/careers/search").provider, "eightfold")
        self.assertEqual(router.detect_only("https://careers.arm.com/search-jobs").provider, "talentbrew")
        self.assertEqual(router.detect_only("https://jobs.intuit.com/search-jobs").provider, "talentbrew")
        self.assertEqual(router.detect_only("https://careers.ti.com/en/sites/CX/jobs").provider, "oracle")

    def test_human_date_parser_handles_amazon_and_citi_formats(self) -> None:
        extractor = AmazonExtractor("amazon", source_url="https://www.amazon.jobs/en/search")

        amazon_date = extractor._parse_datetime("May  7, 2026")
        citi_date = extractor._parse_datetime("2026-5-15")

        self.assertEqual(amazon_date, datetime(2026, 5, 7, tzinfo=UTC))
        self.assertEqual(citi_date, datetime(2026, 5, 15, tzinfo=UTC))

    def test_google_extracts_posted_date_from_embedded_data(self) -> None:
        extractor = GoogleExtractor(
            "google",
            source_url="https://www.google.com/about/careers/applications/jobs/results",
        )
        html = """<script>AF_initDataCallback({key: 'ds:1', data:[[[
            "123","Software Engineer","https://www.google.com/about/careers/applications/signin?jobId=abc&loc=US&title=Software+Engineer",
            [null,"<ul><li>Build things.</li></ul>"],[null,"<p>Python</p>"],"company",null,"Google","en-US",
            [["Austin, TX, USA",["Austin, TX, USA"],"Austin",null,"TX","US"]],
            [null,"<p>Main description.</p>"],[2,3],[1778770806,24000000],[1778770806,24000000],[1778770806,422000000]
        ]]], sideChannel: {}});</script>"""

        jobs = extractor._extract_jobs_from_html(html)

        self.assertEqual(jobs[0]["date_posted"], datetime(2026, 5, 14, 15, 0, 6, 24000, tzinfo=UTC))
        self.assertEqual(jobs[0]["location"], ["Austin, TX, USA"])

    def test_talentbrew_reads_schema_date_posted(self) -> None:
        extractor = TalentBrewExtractor("jobs", source_url="https://jobs.citi.com/search-jobs")
        soup = __import__("bs4").BeautifulSoup(
            '<script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-5-15"}</script>',
            "html.parser",
        )

        self.assertEqual(extractor._job_posting_schema(soup)["datePosted"], "2026-5-15")

    def test_workday_parses_relative_posted_dates(self) -> None:
        extractor = WorkdayExtractor(
            "nvidia",
            source_url="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        )

        posted = extractor._date_posted({"postedOn": "Posted 2 Days Ago"})

        self.assertIsNotNone(posted)
        self.assertEqual((datetime.now(UTC) - posted).days, 2)

    def test_proxy_pool_reads_environment_urls(self) -> None:
        with patch.dict(os.environ, {"JOBFUL_PROXY_URLS": "http://proxy-one:8000, http://proxy-two:8000"}, clear=True):
            pool = ProxyPool.from_environment()

        first_proxy = pool.next_requests_proxy()
        second_proxy = pool.next_requests_proxy()

        self.assertEqual(first_proxy, {"http": "http://proxy-one:8000", "https": "http://proxy-one:8000"})
        self.assertEqual(second_proxy, {"http": "http://proxy-two:8000", "https": "http://proxy-two:8000"})

    def test_phase2_dry_run_does_not_require_redis(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "phase2.py",
                "https://www.amazon.jobs/en/",
                "https://jobs.ashbyhq.com/ashby",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn('"mode": "dry_run"', completed.stdout)
        self.assertIn('"queue": "jobful:high"', completed.stdout)
        self.assertIn('"queue": "jobful:slow"', completed.stdout)

    def test_record_dead_letter_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "dead_letters.jsonl")
            with (
                patch.dict(os.environ, {"JOBFUL_DEAD_LETTER_PATH": path}, clear=False),
                patch("tasks._record_dead_letter_to_redis"),
            ):
                record = record_dead_letter.run(
                    {
                        "source_url": "https://example.com/jobs",
                        "error_type": "ExtractionError",
                        "message": "failed",
                    }
                )

            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as file:
                content = file.read()

        self.assertIn("https://example.com/jobs", content)
        self.assertEqual(record["failure"]["error_type"], "ExtractionError")


if __name__ == "__main__":
    unittest.main()
