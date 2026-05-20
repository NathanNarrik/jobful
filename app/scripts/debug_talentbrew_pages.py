from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.extractors.talentbrew import TalentBrewExtractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print TalentBrew extraction counts by page.")
    parser.add_argument("url")
    parser.add_argument("--pages", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    extractor = TalentBrewExtractor("debug", source_url=args.url, timeout_seconds=12)
    seen: set[str] = set()
    for page in range(1, args.pages + 1):
        html = extractor._fetch_page(page)
        jobs = extractor._jobs_from_html(html, seen)
        print(page, len(jobs), len(seen), extractor._total_pages(html))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
