from __future__ import annotations

import argparse
import re
from urllib.parse import urljoin

import requests


SCRIPT_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)", re.IGNORECASE)
URL_RE = re.compile(
    r"(?i)(?:https?://[^\"'<> ]+|/[A-Za-z0-9_./-]*(?:api|job|jobs|graphql|opportun|search|position)[A-Za-z0-9_./?=&:%-]*)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search page JS bundles for API-looking strings.")
    parser.add_argument("url")
    parser.add_argument("--term", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    headers = {"User-Agent": "Mozilla/5.0"}
    page = requests.get(args.url, headers=headers, timeout=25)
    page.raise_for_status()
    scripts = [urljoin(page.url, src) for src in SCRIPT_RE.findall(page.text)]
    terms = [term.lower() for term in (args.term or ["api", "graphql", "opportun", "job", "search"])]
    print(f"scripts={len(scripts)}")

    for script_url in scripts:
        response = requests.get(script_url, headers=headers, timeout=25)
        text = response.text
        hits = [term for term in terms if term in text.lower()]
        if not hits:
            continue
        print(f"SCRIPT {script_url} LEN {len(text)} HITS {hits}")
        for match in sorted(set(URL_RE.findall(text)))[:100]:
            print(match.encode("ascii", "ignore").decode("ascii"))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
