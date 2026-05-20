from __future__ import annotations

import json
import os

from app.normalizers.ollama import normalize_with_ollama


SMOKE_DESCRIPTION = (
    "Software Engineering Intern role for undergraduate students graduating in 2026. "
    "Visa sponsorship is available. Remote role requiring Python and SQL."
)


def main() -> int:
    os.environ.setdefault("JOBFUL_USE_OLLAMA", "true")
    normalization = normalize_with_ollama(SMOKE_DESCRIPTION)
    if normalization is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": "Ollama did not return a valid JobNormalization. Check Ollama install, model name, and server URL.",
                    "model": os.getenv("JOBFUL_OLLAMA_MODEL", "mistral"),
                    "url": os.getenv("JOBFUL_OLLAMA_URL", "http://localhost:11434/api/generate"),
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "normalization": normalization.model_dump(mode="json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
