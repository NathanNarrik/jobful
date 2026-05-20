from __future__ import annotations

import json
import os
from urllib import request

from app.models import JobNormalization


DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 120


def ollama_enabled() -> bool:
    return os.getenv("JOBFUL_USE_OLLAMA", "").lower() in {"1", "true", "yes"}


def normalize_with_ollama(cleaned_description: str, *, model: str | None = None) -> JobNormalization | None:
    if not ollama_enabled():
        return None

    model_name = model or os.getenv("JOBFUL_OLLAMA_MODEL", "mistral")
    payload = {
        "model": model_name,
        "prompt": _prompt(cleaned_description),
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 512},
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        os.getenv("JOBFUL_OLLAMA_URL", DEFAULT_OLLAMA_URL),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        timeout = float(os.getenv("JOBFUL_OLLAMA_TIMEOUT", str(DEFAULT_OLLAMA_TIMEOUT_SECONDS)))
        with request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        generated = body.get("response")
        if not isinstance(generated, str):
            return None
        parsed = _parse_json_object(generated)
        parsed.setdefault("academic_levels", [])
        parsed.setdefault("degree_requirements", [])
        parsed.setdefault("visa_status", _visa_status_from_bool(parsed.get("visa_sponsorship")))
        parsed.setdefault("normalization_status", "COMPLETE")
        parsed.setdefault("confidence", 0.8)
        parsed.setdefault("review_reasons", [])
        return JobNormalization.model_validate(parsed)
    except Exception:
        return None


def _prompt(cleaned_description: str) -> str:
    return (
        "Return exactly one JSON object and nothing else. Do not use markdown. "
        "Use this schema with all keys present: "
        "{\"program_type\":\"internship|new_grad|experienced|other\","
        "\"academic_levels\":[\"freshman|sophomore|junior|senior|undergraduate|masters|phd|new_grad\"],"
        "\"degree_requirements\":[\"bachelors|masters|phd\"],"
        "\"required_grad_years\":[2026],"
        "\"visa_sponsorship\":true,"
        "\"visa_status\":\"sponsors|does_not_sponsor|requires_authorization|opt_cpt_allowed|not_mentioned|unclear\","
        "\"required_skills\":[\"python\"],"
        "\"nice_to_have_skills\":[],"
        "\"min_gpa\":null,"
        "\"clearance_required\":false,"
        "\"remote_type\":\"remote|hybrid|onsite|unknown\","
        "\"confidence\":0.8,"
        "\"review_reasons\":[]}"
        "\nJob description:\n"
        f"{cleaned_description[: int(os.getenv('JOBFUL_OLLAMA_MAX_CHARS', '4000'))]}"
    )


def _visa_status_from_bool(value: object) -> str:
    if value is True:
        return "sponsors"
    if value is False:
        return "does_not_sponsor"
    return "not_mentioned"


def _parse_json_object(value: str) -> dict:
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("No JSON object found", value, 0)
    parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("JSON value is not an object", value, start)
    return parsed
