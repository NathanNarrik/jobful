from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from proxy import ProxyPool
from queueing import QueueName, choose_queue, get_backoff_delay
from router import AtsRouter
from tasks import record_dead_letter


class Phase2Tests(unittest.TestCase):
    def test_choose_queue_classifies_priority_sources(self) -> None:
        self.assertEqual(choose_queue("https://www.amazon.jobs/en/").queue, QueueName.HIGH)
        self.assertEqual(choose_queue("https://jobs.ashbyhq.com/ashby").queue, QueueName.SLOW)
        self.assertEqual(choose_queue("https://boards.greenhouse.io/airbnb").queue, QueueName.STANDARD)

    def test_backoff_increases_with_jitter(self) -> None:
        delay = get_backoff_delay(3, base=2.0, cap=300.0)
        self.assertGreaterEqual(delay, 8.0)
        self.assertLessEqual(delay, 8.8)

    def test_detect_only_returns_route_without_extracting(self) -> None:
        router = AtsRouter()

        self.assertEqual(router.detect_only("https://boards.greenhouse.io/airbnb").provider, "greenhouse")
        self.assertEqual(router.detect_only("https://jobs.lever.co/Flex").provider, "lever")
        self.assertEqual(router.detect_only("https://jobs.ashbyhq.com/ashby").provider, "ashby")

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
