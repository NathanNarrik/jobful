from __future__ import annotations

import re
import unicodedata

from app.extractors.text import html_to_text


BOILERPLATE_PATTERNS = [
    re.compile(r"(?is)\bwe are an equal opportunity employer\b.*?(?=\n\n|$)"),
    re.compile(r"(?is)\bequal employment opportunity\b.*?(?=\n\n|$)"),
    re.compile(r"(?is)\bEEO\b.*?(?=\n\n|$)"),
    re.compile(r"(?is)\breasonable accommodation\b.*?(?=\n\n|$)"),
]


def clean_description(raw_description: str, description_html: str | None = None) -> str:
    source = description_html or raw_description
    text = html_to_text(source)
    text = unicodedata.normalize("NFKC", text)
    text = _strip_boilerplate(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_boilerplate(text: str) -> str:
    cleaned = text
    for pattern in BOILERPLATE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned
