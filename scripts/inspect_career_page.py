from __future__ import annotations

import re
import sys
from urllib.parse import urljoin

import requests


SCRIPT_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)", re.IGNORECASE)
API_RE = re.compile(
    r"(?i)(?:https?://[^\"'<> ]+|/[A-Za-z0-9_./-]*(?:api|jobs|requisition|position|search)[A-Za-z0-9_./?=&:%-]*)"
)


def main() -> int:
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in sys.argv[1:]:
        response = requests.get(url, headers=headers, timeout=20)
        print(f"URL {url}")
        print(f"STATUS {response.status_code} CT {response.headers.get('content-type')} LEN {len(response.text)}")
        scripts = [urljoin(response.url, src) for src in SCRIPT_RE.findall(response.text)]
        print("SCRIPTS")
        for script in scripts[:30]:
            print(script)
        print("API-ish")
        for match in sorted(set(API_RE.findall(response.text)))[:80]:
            print(urljoin(response.url, match))
        print("HEAD", response.text[:300].replace("\n", " "))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
