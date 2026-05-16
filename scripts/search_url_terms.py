from __future__ import annotations

import argparse

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch a URL and print context around terms.")
    parser.add_argument("url")
    parser.add_argument("terms", nargs="+")
    parser.add_argument("--context", type=int, default=700)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    response = requests.get(args.url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    text = response.text
    for term in args.terms:
        search_from = 0
        printed = 0
        while printed < 3:
            index = text.lower().find(term.lower(), search_from)
            if index == -1:
                if printed == 0:
                    print(f"TERM {term} not found")
                break
            start = max(0, index - args.context)
            end = min(len(text), index + args.context)
            snippet = text[start:end].encode("ascii", "ignore").decode("ascii")
            print(f"TERM {term} IDX {index}")
            print(snippet)
            print()
            search_from = index + len(term)
            printed += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
