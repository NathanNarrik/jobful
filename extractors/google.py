from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from models import JobListing


SIGNIN_RE = re.compile(r"https://www\.google\.com/about/careers/applications/signin\?[^\"'<> ]+")


class GoogleExtractor(BaseExtractor):
    provider = "google"
    results_url_template = "https://www.google.com/about/careers/applications/jobs/results?page={page}"
    max_pages = 20

    def extract(self) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        for page in range(1, self.max_pages + 1):
            html = self._get_text(self.results_url_template.format(page=page))
            page_jobs = self._extract_jobs_from_html(html)
            new_jobs = [job for job in page_jobs if job["ats_job_id"] not in seen_ids]
            if not new_jobs:
                break

            for job in new_jobs:
                seen_ids.add(job["ats_job_id"])
                try:
                    jobs.append(
                        self._build_listing(
                            company_name="Google",
                            job_title=job["job_title"],
                            job_url=job["job_url"],
                            ats_job_id=job["ats_job_id"],
                            location=job["location"],
                            raw_description=job["job_title"],
                            description_html=None,
                            employment_type=None,
                            departments=[],
                            date_posted=None,
                        )
                    )
                except (ValidationError, ValueError) as exc:
                    self.logger.error("Failed mapping Google job", exc_info=True)
                    raise ExtractionError("Malformed Google job payload", raw_payload=job) from exc

        if not jobs:
            raise ExtractionError("No Google jobs discovered from careers results pages")

        self.logger.info("Fetched %s Google jobs", len(jobs), extra={"company": "Google"})
        return jobs

    def _get_text(self, url: str) -> str:
        response = self.session.get(url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.text

    def _extract_jobs_from_html(self, html: str) -> list[dict[str, object]]:
        jobs: list[dict[str, object]] = []
        for raw_url in SIGNIN_RE.findall(html):
            url = unescape(raw_url).replace("\\u003d", "=").replace("\\u0026", "&")
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            job_id = unquote(query.get("jobId", [""])[0]).strip()
            title = unquote(query.get("title", [""])[0]).replace("+", " ").strip()
            location = unquote(query.get("loc", [""])[0]).strip()
            if not job_id or not title:
                continue

            jobs.append(
                {
                    "ats_job_id": job_id,
                    "job_title": title,
                    "job_url": urljoin("https://www.google.com", parsed.path + "?" + parsed.query),
                    "location": [location or "Unspecified"],
                }
            )
        return jobs
