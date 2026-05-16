from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterable

from pydantic import TypeAdapter

from models import JobListing
from router import AtsRouter, UnsupportedAtsError


SAMPLE_CAREER_URLS = [
    "https://boards.greenhouse.io/airbnb",
    "https://jobs.lever.co/Flex",
    "https://boards.greenhouse.io/stripe",
]


def extract_urls(career_urls: Iterable[str]) -> list[JobListing]:
    router = AtsRouter()
    listings: list[JobListing] = []

    for career_url in career_urls:
        try:
            listings.extend(router.extract(career_url))
        except UnsupportedAtsError:
            logging.exception("Unsupported ATS URL skipped: %s", career_url)
        except Exception:
            logging.exception("Extraction failed for URL skipped: %s", career_url)

    return listings


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    career_urls = sys.argv[1:] or SAMPLE_CAREER_URLS
    listings = extract_urls(career_urls)

    adapter = TypeAdapter(list[JobListing])
    print(json.dumps(adapter.dump_python(listings, mode="json"), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
