from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from extractors.base import BaseExtractor, ExtractionError
from extractors.text import html_to_text
from models import JobListing


class GreenhouseExtractor(BaseExtractor):
    provider = "greenhouse"
    api_url_template = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    COMPANY_BY_TOKEN = {
        "arizeai": "Arize AI",
        "adyen": "Adyen",
        "algolia": "Algolia",
        "amplitude": "Amplitude",
        "astranis": "Astranis",
        "aurorainnovation": "Aurora",
        "blackduck": "Black Duck",
        "bitwarden": "Bitwarden",
        "canonical": "Canonical",
        "cerebrassystems": "Cerebras",
        "circleci": "CircleCI",
        "clickhouse": "ClickHouse",
        "collibra": "Collibra",
        "coreweave": "CoreWeave",
        "descript": "Descript",
        "digitalocean98": "DigitalOcean",
        "dremio": "Dremio",
        "dropbox": "Dropbox",
        "epirus": "Epirus",
        "epicgames": "Epic Games",
        "fiveringsllc": "Five Rings",
        "figureai": "Figure AI",
        "fireworksai": "Fireworks AI",
        "gemini": "Gemini",
        "grafanalabs": "Grafana Labs",
        "gofundme": "GoFundMe",
        "helsing": "Helsing",
        "jfrog": "JFrog",
        "launchdarkly": "LaunchDarkly",
        "materialize": "Materialize",
        "mercury": "Mercury",
        "mixpanel": "Mixpanel",
        "monzo": "Monzo",
        "n26": "N26",
        "netlify": "Netlify",
        "nintendo": "Nintendo",
        "nubank": "Nubank",
        "planetlabs": "Planet Labs",
        "planetscale": "PlanetScale",
        "riotgames": "Riot Games",
        "singlestore": "SingleStore",
        "runpod": "Runpod",
        "sourcegraph91": "Sourcegraph",
        "starburst": "Starburst",
        "squarespace": "Squarespace",
        "tailscale": "Tailscale",
        "togetherai": "Together AI",
        "twitch": "Twitch",
        "typeform": "Typeform",
        "unity3d": "Unity",
        "veracode": "Veracode",
        "vast": "Vast",
        "wing": "Wing",
        "xai": "xAI",
        "2k": "2K",
    }

    def extract(self) -> list[JobListing]:
        url = self.api_url_template.format(board_token=self.board_token)
        payload = self._get_json(url)

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            self.logger.error("Unexpected Greenhouse payload shape for board %s", self.board_token)
            raise ExtractionError("Unexpected Greenhouse payload schema", raw_payload=payload)

        company_name = self.COMPANY_BY_TOKEN.get(self.board_token, str(payload.get("name") or self.board_token))
        listings: list[JobListing] = []

        for job in payload["jobs"]:
            if not isinstance(job, dict):
                raise ExtractionError("Greenhouse job payload is not an object", raw_payload=job)

            try:
                listings.append(self._map_job(company_name, job))
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                self.logger.error(
                    "Failed mapping Greenhouse job on board %s",
                    self.board_token,
                    exc_info=True,
                )
                raise ExtractionError("Malformed Greenhouse job payload", raw_payload=job) from exc

        self.logger.info("Fetched %s Greenhouse jobs", len(listings), extra={"company": company_name})
        return listings

    def _map_job(self, company_name: str, job: dict[str, Any]) -> JobListing:
        job_id = str(job["id"])
        description_html = str(job.get("content") or "")

        return self._build_listing(
            company_name=company_name,
            job_title=self._required_string(job, "title"),
            job_url=self._job_url(job, job_id),
            ats_job_id=job_id,
            location=self._locations(job),
            raw_description=html_to_text(description_html),
            description_html=description_html or None,
            employment_type=None,
            departments=self._departments(job),
            date_posted=self._parse_datetime(job.get("updated_at")),
        )

    def _job_url(self, job: dict[str, Any], job_id: str) -> str:
        absolute_url = job.get("absolute_url")
        if isinstance(absolute_url, str) and absolute_url.strip():
            return absolute_url.strip()
        return f"https://boards.greenhouse.io/{self.board_token}/jobs/{job_id}"

    def _locations(self, job: dict[str, Any]) -> list[str]:
        location = job.get("location")
        if isinstance(location, dict) and location.get("name"):
            return [str(location["name"]).strip()]

        offices = job.get("offices")
        if isinstance(offices, list):
            return [
                str(office["name"]).strip()
                for office in offices
                if isinstance(office, dict) and office.get("name")
            ] or ["Unspecified"]

        return ["Unspecified"]

    def _departments(self, job: dict[str, Any]) -> list[str]:
        departments = job.get("departments")
        if not isinstance(departments, list):
            return []

        return [
            str(department["name"]).strip()
            for department in departments
            if isinstance(department, dict) and department.get("name")
        ]
