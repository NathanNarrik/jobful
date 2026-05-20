from __future__ import annotations

import argparse
import re
from pathlib import Path

import requests


API_RE = re.compile(
    r"(?i)(?:https?://[^\"'<> ]+|/[A-Za-z0-9_./-]*(?:api|job|jobs|position|search|opportun|requisition)[A-Za-z0-9_./?=&:%-]*)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe URLs and print compact response metadata.")
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--save-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,*/*"}

    if args.save_dir:
        args.save_dir.mkdir(parents=True, exist_ok=True)

    for index, url in enumerate(args.urls):
        response = session.get(url, headers=headers, timeout=25)
        print(f"URL {url}")
        print(f"FINAL {response.url}")
        print(f"STATUS {response.status_code} CT {response.headers.get('content-type')} LEN {len(response.text)}")
        print("MATCHES")
        for match in sorted(set(API_RE.findall(response.text)))[:80]:
            print(match)
        print("HEAD", response.text[:800].replace("\n", " "))
        if args.save_dir:
            out = args.save_dir / f"probe_{index}.txt"
            out.write_text(response.text, encoding="utf-8", errors="replace")
            print(f"SAVED {out}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
