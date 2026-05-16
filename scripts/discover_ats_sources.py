from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import requests


HEADER_RE = re.compile(r"^\s*(?:top\s+\d+|compiled|includes)\b", re.IGNORECASE)
RANKED_LINE_RE = re.compile(r"^\s*\d+\.\s*(?P<name>.+?)\s*$")
NON_TOKEN_RE = re.compile(r"[^a-z0-9]+")
SUFFIXES = {
    "ai",
    "america",
    "bank",
    "capital",
    "co",
    "company",
    "corp",
    "corporation",
    "financial",
    "group",
    "holdings",
    "inc",
    "incorporated",
    "labs",
    "llc",
    "lp",
    "management",
    "partners",
    "software",
    "systems",
    "technologies",
    "technology",
}
KNOWN_TOKEN_ALIASES = {
    "Alphabet": ["google", "alphabet"],
    "Amazon": ["amazon", "amazonjobs"],
    "Anduril": ["andurilindustries", "anduril"],
    "Box": ["boxinc", "box"],
    "DoorDash": ["doordashusa", "doordash"],
    "HubSpot": ["hubspotjobs", "hubspot"],
    "TripActions": ["tripactions", "navan"],
    "Wiz": ["wizinc", "wiz"],
}


@dataclass(frozen=True)
class DiscoveryHit:
    company_name: str
    ats_provider: str
    board_token: str
    source_url: str
    job_count: int


def parse_company_file(path: Path) -> list[str]:
    companies: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or HEADER_RE.match(line):
            continue

        match = RANKED_LINE_RE.match(line)
        if match:
            companies.append(match.group("name").strip())

    return companies


def candidate_tokens(company_name: str) -> list[str]:
    aliases = KNOWN_TOKEN_ALIASES.get(company_name, [])
    words = tokenize(company_name)
    trimmed_words = [word for word in words if word not in SUFFIXES]
    variants = [
        "".join(words),
        "-".join(words),
        "".join(trimmed_words),
        "-".join(trimmed_words),
    ]
    if words:
        variants.append(words[0])
    if len(words) >= 2:
        variants.append("".join(words[:2]))
        variants.append("-".join(words[:2]))

    seen: set[str] = set()
    tokens: list[str] = []
    for token in [*aliases, *variants]:
        normalized = token.strip("-").lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            tokens.append(normalized)
    return tokens[:8]


def tokenize(company_name: str) -> list[str]:
    without_parens = re.sub(r"\([^)]*\)", "", company_name)
    normalized = without_parens.replace("&", " and ")
    return [
        token
        for token in NON_TOKEN_RE.sub(" ", normalized.lower()).split()
        if token and token not in {"the"}
    ]


def discover_company(company_name: str, timeout_seconds: float) -> DiscoveryHit | None:
    for token in candidate_tokens(company_name):
        hit = probe_greenhouse(company_name, token, timeout_seconds)
        if hit:
            return hit
        hit = probe_lever(company_name, token, timeout_seconds)
        if hit:
            return hit
        hit = probe_ashby(company_name, token, timeout_seconds)
        if hit:
            return hit
    return None


def probe_greenhouse(company_name: str, token: str, timeout_seconds: float) -> DiscoveryHit | None:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false"
    data = get_json(url, timeout_seconds)
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):
        return DiscoveryHit(
            company_name=company_name,
            ats_provider="greenhouse",
            board_token=token,
            source_url=f"https://boards.greenhouse.io/{token}",
            job_count=len(data["jobs"]),
        )
    return None


def probe_lever(company_name: str, token: str, timeout_seconds: float) -> DiscoveryHit | None:
    url = f"https://api.lever.co/v0/postings/{token}?mode=json&limit=1"
    data = get_json(url, timeout_seconds)
    if isinstance(data, list):
        return DiscoveryHit(
            company_name=company_name,
            ats_provider="lever",
            board_token=token,
            source_url=f"https://jobs.lever.co/{token}",
            job_count=len(data),
        )
    return None


def probe_ashby(company_name: str, token: str, timeout_seconds: float) -> DiscoveryHit | None:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    data = get_json(url, timeout_seconds)
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):
        return DiscoveryHit(
            company_name=company_name,
            ats_provider="ashby",
            board_token=token,
            source_url=f"https://jobs.ashbyhq.com/{token}",
            job_count=len(data["jobs"]),
        )
    return None


def get_json(url: str, timeout_seconds: float) -> object | None:
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=timeout_seconds,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def discover_sources(
    companies: Iterable[str],
    *,
    workers: int,
    timeout_seconds: float,
) -> tuple[list[DiscoveryHit], list[str]]:
    company_list = list(companies)
    hits: list[DiscoveryHit] = []
    unmatched: list[str] = []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(discover_company, company_name, timeout_seconds): company_name
            for company_name in company_list
        }
        for future in as_completed(futures):
            company_name = futures[future]
            hit = future.result()
            if hit is None:
                unmatched.append(company_name)
            else:
                hits.append(hit)

    return sorted(hits, key=lambda hit: hit.company_name.lower()), sorted(unmatched)


def discover_sources_incremental(
    companies: Iterable[str],
    *,
    workers: int,
    timeout_seconds: float,
    output_dir: Path,
) -> tuple[list[DiscoveryHit], list[str]]:
    company_list = list(companies)
    hits: list[DiscoveryHit] = []
    unmatched: list[str] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    hits_path = output_dir / "discovery_hits.jsonl"
    unmatched_path = output_dir / "unmatched_companies.txt"
    sources_path = output_dir / "discovered_sources.txt"

    hits_path.write_text("", encoding="utf-8")
    unmatched_path.write_text("", encoding="utf-8")
    sources_path.write_text("", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(discover_company, company_name, timeout_seconds): company_name
            for company_name in company_list
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            company_name = futures[future]
            hit = future.result()
            if hit is None:
                unmatched.append(company_name)
                with unmatched_path.open("a", encoding="utf-8") as file:
                    file.write(f"{company_name}\n")
            else:
                hits.append(hit)
                with hits_path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(asdict(hit)) + "\n")
                with sources_path.open("a", encoding="utf-8") as file:
                    file.write(f"{hit.source_url}\n")

            if completed % 50 == 0:
                print(
                    json.dumps(
                        {
                            "processed": completed,
                            "hits": len(hits),
                            "unmatched": len(unmatched),
                        }
                    ),
                    flush=True,
                )

    write_outputs(
        sorted(hits, key=lambda hit: hit.company_name.lower()),
        sorted(unmatched),
        output_dir,
    )
    return sorted(hits, key=lambda hit: hit.company_name.lower()), sorted(unmatched)


def write_outputs(hits: list[DiscoveryHit], unmatched: list[str], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "discovered_sources.txt").write_text(
        "\n".join(hit.source_url for hit in hits) + "\n",
        encoding="utf-8",
    )
    (output_dir / "discovery_hits.json").write_text(
        json.dumps([asdict(hit) for hit in hits], indent=2),
        encoding="utf-8",
    )
    (output_dir / "unmatched_companies.txt").write_text(
        "\n".join(unmatched) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover supported ATS sources from company names.")
    parser.add_argument("company_file", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("outputs/company_discovery"))
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    companies = parse_company_file(args.company_file)
    hits, unmatched = discover_sources_incremental(
        companies,
        workers=args.workers,
        timeout_seconds=args.timeout,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "company_count": len(companies),
                "discovered_source_count": len(hits),
                "unmatched_count": len(unmatched),
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
