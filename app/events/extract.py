from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.models import (
    EventLocationType,
    EventPullFailure,
    EventPullResult,
    EventPullSourceResult,
    EventSourceConfig,
    RecruitingEventListing,
)
from app.events.sources import DEFAULT_EVENT_SOURCES


DEFAULT_OUTPUT_DIR = Path("outputs")
EVENT_SCHEMA_TYPES = {"Event", "BusinessEvent", "EducationEvent"}


def extract_event_sources(
    sources: Iterable[EventSourceConfig],
    *,
    timeout_seconds: float = 10.0,
    workers: int = 8,
) -> EventPullResult:
    deduped_sources = dedupe_sources(sources)
    events: list[RecruitingEventListing] = []
    failures: list[EventPullFailure] = []
    source_results: list[EventPullSourceResult] = []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(extract_single_event_source, source, timeout_seconds): source
            for source in deduped_sources
        }
        for future in as_completed(futures):
            source = futures[future]
            extracted, failure, source_result = future.result()
            source_results.append(source_result)
            if failure is not None:
                logging.warning(
                    "Event source skipped: %s (%s: %s)",
                    source.event_page_url,
                    failure.error_type,
                    failure.message,
                )
                failures.append(failure)
                continue
            logging.info("Extracted %s events from %s", len(extracted), source.event_page_url)
            events.extend(extracted)

    return EventPullResult(
        generated_at=datetime.now(UTC),
        source_count=len(deduped_sources),
        successful_source_count=len(deduped_sources) - len(failures),
        failed_source_count=len(failures),
        event_count=len(events),
        sources=sorted(source_results, key=lambda item: item.source_url.lower()),
        events=events,
        failures=failures,
    )


def extract_single_event_source(
    source: EventSourceConfig,
    timeout_seconds: float = 10.0,
) -> tuple[list[RecruitingEventListing], EventPullFailure | None, EventPullSourceResult]:
    try:
        events = CompanyEventPageExtractor(source, timeout_seconds=timeout_seconds).extract()
        return events, None, EventPullSourceResult(
            source_url=str(source.event_page_url),
            firm_name=source.firm_name,
            firm_kind=source.firm_kind,
            source_provider=source.source_provider,
            status="success",
            event_count=len(events),
        )
    except Exception as exc:
        logging.exception("Event extraction failed for URL skipped: %s", source.event_page_url)
        failure = EventPullFailure(
            source_url=str(source.event_page_url),
            firm_name=source.firm_name,
            firm_kind=source.firm_kind,
            source_provider=source.source_provider,
            error_type=exc.__class__.__name__,
            message=str(exc),
        )
        return [], failure, EventPullSourceResult(
            source_url=str(source.event_page_url),
            firm_name=source.firm_name,
            firm_kind=source.firm_kind,
            source_provider=source.source_provider,
            status="failed",
            event_count=0,
            error_type=failure.error_type,
            message=failure.message,
        )


class CompanyEventPageExtractor:
    def __init__(
        self,
        source: EventSourceConfig,
        *,
        timeout_seconds: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.source = source
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def extract(self) -> list[RecruitingEventListing]:
        response = self.session.get(
            str(self.source.event_page_url),
            headers={"Accept": "text/html,application/xhtml+xml,text/calendar,*/*", "User-Agent": "JobfulEvents/1.0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/calendar" in content_type or str(self.source.event_page_url).lower().endswith(".ics"):
            return self._dedupe(self._extract_ics(response.text, str(self.source.event_page_url)))

        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        events = []
        events.extend(self._extract_json_ld(soup))
        events.extend(self._extract_linked_calendars(soup))
        events.extend(self._extract_embedded_json(soup))
        events.extend(self._extract_html_event_cards(soup))
        return self._dedupe(events)

    def _extract_json_ld(self, soup: BeautifulSoup) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            payload = self._loads_json(script.string or script.get_text(" ", strip=True))
            if payload is None:
                continue
            for item in self._walk_json(payload):
                if self._is_schema_event(item):
                    event = self._event_from_mapping(item, fallback_url=str(self.source.event_page_url))
                    if event is not None:
                        events.append(event)
        return events

    def _extract_linked_calendars(self, soup: BeautifulSoup) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            if ".ics" not in href.lower() and "ical" not in href.lower():
                continue
            url = urljoin(str(self.source.event_page_url), href)
            try:
                response = self.session.get(
                    url,
                    headers={"Accept": "text/calendar,*/*", "User-Agent": "JobfulEvents/1.0"},
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                events.extend(self._extract_ics(response.text, url))
            except requests.RequestException:
                continue
        return events

    def _extract_embedded_json(self, soup: BeautifulSoup) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        for script in soup.find_all("script"):
            text = script.string or script.get_text(" ", strip=True)
            stripped = text.strip()
            if not stripped or stripped[0] not in "[{":
                continue
            payload = self._loads_json(stripped)
            if payload is None:
                continue
            for item in self._walk_json(payload):
                if self._looks_like_event(item):
                    event = self._event_from_mapping(item, fallback_url=str(self.source.event_page_url))
                    if event is not None:
                        events.append(event)
        return events

    def _extract_html_event_cards(self, soup: BeautifulSoup) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        selectors = [
            "[class*=event]",
            "[id*=event]",
            "article",
            "li",
        ]
        for selector in selectors:
            for element in soup.select(selector):
                text = normalize_space(element.get_text(" ", strip=True))
                if len(text) < 20 or not self._contains_event_language(text):
                    continue
                heading = element.find(["h1", "h2", "h3", "h4"])
                title = normalize_space(heading.get_text(" ", strip=True)) if heading else text[:120]
                time_element = element.find("time")
                starts_at = self._parse_datetime(time_element.get("datetime") if time_element else None) or self._parse_datetime(text)
                if starts_at is None:
                    continue
                link = element.find("a", href=True)
                event_url = urljoin(str(self.source.event_page_url), str(link["href"])) if link else str(self.source.event_page_url)
                event = self._build_event(
                    event_title=title,
                    event_url=event_url,
                    registration_url=event_url,
                    source_event_id=None,
                    event_type=event_type_from_text(title, text),
                    audience_tags=audience_tags_from_text(text),
                    location=location_from_text(text),
                    location_type=location_type_from_text(text),
                    starts_at=starts_at,
                    ends_at=None,
                    timezone=None,
                    description=text,
                    raw_payload=None,
                )
                events.append(event)
        return events[:50]

    def _extract_ics(self, content: str, source_url: str) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        for block in ics_event_blocks(content):
            summary = block.get("SUMMARY")
            starts_at = parse_ics_datetime(block.get("DTSTART"))
            if not summary or starts_at is None:
                continue
            description = block.get("DESCRIPTION")
            location = self._string_list(block.get("LOCATION"))
            event_url = block.get("URL") or source_url
            events.append(
                self._build_event(
                    event_title=summary,
                    event_url=event_url,
                    registration_url=event_url,
                    source_event_id=block.get("UID"),
                    event_type=event_type_from_text(summary, description or ""),
                    audience_tags=audience_tags_from_text(f"{summary} {description or ''}"),
                    location=location,
                    location_type=location_type_from_text(" ".join(location) or description or ""),
                    starts_at=starts_at,
                    ends_at=parse_ics_datetime(block.get("DTEND")),
                    timezone=block.get("TZID"),
                    description=description,
                    raw_payload=block,
                )
            )
        return events

    def _event_from_mapping(self, item: dict[str, Any], *, fallback_url: str) -> RecruitingEventListing | None:
        title = first_string(item, "name", "title", "headline", "summary")
        starts_at = self._parse_datetime(first_value(item, "startDate", "start_date", "startsAt", "startTime", "date"))
        if not title or starts_at is None:
            return None
        event_url = first_string(item, "url", "eventUrl", "canonicalUrl", "link") or fallback_url
        registration_url = first_string(item, "registrationUrl", "registration_url", "applyUrl", "rsvpUrl") or event_url
        location = self._location_from_mapping(item)
        description = first_string(item, "description", "body", "shortDescription", "details")
        event_type = first_string(item, "eventType", "event_type", "category", "type") or event_type_from_text(title, description or "")
        source_event_id = first_string(item, "identifier", "id", "uid", "eventId")
        return self._build_event(
            event_title=title,
            event_url=event_url,
            registration_url=registration_url,
            source_event_id=source_event_id,
            event_type=event_type_slug(event_type),
            audience_tags=audience_tags_from_text(f"{title} {description or ''}"),
            location=location,
            location_type=location_type_from_text(" ".join(location) or description or title),
            starts_at=starts_at,
            ends_at=self._parse_datetime(first_value(item, "endDate", "end_date", "endsAt", "endTime")),
            timezone=first_string(item, "timezone", "timeZone", "tz"),
            description=description,
            raw_payload=item,
        )

    def _build_event(
        self,
        *,
        event_title: str,
        event_url: str,
        registration_url: str | None,
        source_event_id: str | None,
        event_type: str,
        audience_tags: list[str],
        location: list[str],
        location_type: EventLocationType,
        starts_at: datetime,
        ends_at: datetime | None,
        timezone: str | None,
        description: str | None,
        raw_payload: dict[str, Any] | None,
    ) -> RecruitingEventListing:
        normalized_location = location or ["Virtual"] if location_type == "virtual" else location or ["Unspecified"]
        return RecruitingEventListing(
            firm_name=self.source.firm_name,
            firm_kind=self.source.firm_kind,
            event_title=event_title,
            event_url=event_url,
            registration_url=registration_url,
            source_provider=self.source.source_provider,
            source_event_id=source_event_id,
            event_type=event_type_slug(event_type),
            audience_tags=sorted(set(audience_tags)),
            location=normalized_location,
            location_type=location_type,
            starts_at=starts_at if starts_at.tzinfo else starts_at.replace(tzinfo=UTC),
            ends_at=ends_at if ends_at is None or ends_at.tzinfo else ends_at.replace(tzinfo=UTC),
            timezone=timezone,
            description=description,
            raw_payload=raw_payload,
            content_hash=self._content_hash(event_title, starts_at, event_url, source_event_id),
            extracted_at=datetime.now(UTC),
        )

    def _content_hash(self, event_title: str, starts_at: datetime, event_url: str, source_event_id: str | None) -> str:
        stable_id = source_event_id or f"{self.source.firm_name}|{event_title}|{starts_at.isoformat()}|{event_url}"
        return hashlib.sha256(stable_id.encode("utf-8")).hexdigest()

    def _location_from_mapping(self, item: dict[str, Any]) -> list[str]:
        value = first_value(item, "location", "eventLocation", "venue")
        if isinstance(value, dict):
            name = first_string(value, "name", "displayName")
            address = first_value(value, "address")
            address_text = address_from_value(address)
            return [part for part in [name, address_text] if part]
        return self._string_list(value)

    def _is_schema_event(self, item: dict[str, Any]) -> bool:
        value = item.get("@type") or item.get("type")
        types = value if isinstance(value, list) else [value]
        return any(str(item_type).split("/")[-1] in EVENT_SCHEMA_TYPES for item_type in types if item_type)

    def _looks_like_event(self, item: dict[str, Any]) -> bool:
        has_title = any(key in item for key in ("name", "title", "headline", "summary"))
        has_date = any(key in item for key in ("startDate", "start_date", "startsAt", "startTime", "date"))
        return has_title and has_date

    def _parse_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, (int, float)):
            timestamp = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(timestamp, UTC)
        text = normalize_space(str(value)).replace("Z", "+00:00")
        if not text:
            return None
        if match := re.search(r"\b(\d{4}-\d{2}-\d{2}(?:[T ][0-9:]{4,8}(?:[+-][0-9:]+)?)?)\b", text):
            text = match.group(1)
        for candidate in (text, text.replace(" ", "T")):
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                pass
        for date_format in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y%m%d"):
            try:
                return datetime.strptime(text, date_format).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None

    def _walk_json(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from self._walk_json(nested)
        elif isinstance(value, list):
            for item in value:
                yield from self._walk_json(item)

    def _loads_json(self, text: str) -> Any | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _contains_event_language(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ("event", "webinar", "career fair", "info session", "recruit", "workshop"))

    def _string_list(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [normalize_space(value)] if normalize_space(value) else []
        if isinstance(value, list):
            return [normalize_space(str(item)) for item in value if normalize_space(str(item))]
        return [normalize_space(str(value))]

    def _dedupe(self, events: list[RecruitingEventListing]) -> list[RecruitingEventListing]:
        seen: set[str] = set()
        deduped: list[RecruitingEventListing] = []
        for event in events:
            if event.content_hash in seen:
                continue
            seen.add(event.content_hash)
            deduped.append(event)
        return sorted(deduped, key=lambda event: event.starts_at)


def dedupe_sources(sources: Iterable[EventSourceConfig]) -> list[EventSourceConfig]:
    seen: set[str] = set()
    deduped: list[EventSourceConfig] = []
    for source in sources:
        source_url = str(source.event_page_url).strip()
        if not source_url or source_url in seen:
            continue
        seen.add(source_url)
        deduped.append(source)
    return deduped


def read_source_file(path: Path) -> list[EventSourceConfig]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Event source file must contain a JSON array")
    return [EventSourceConfig.model_validate(item) for item in payload]


def write_result(result: EventPullResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")


def default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"jobful_events_pull_{timestamp}.json"


def parse_ics_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if ":" in text:
        text = text.rsplit(":", maxsplit=1)[-1]
    if text.endswith("Z"):
        text = text[:-1]
        timezone = UTC
    else:
        timezone = UTC
    for date_format in ("%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone)
        except ValueError:
            continue
    return None


def ics_event_blocks(content: str) -> list[dict[str, str]]:
    lines = unfold_ics_lines(content)
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        base_key = key.split(";", maxsplit=1)[0].upper()
        current[base_key] = clean_ics_text(value)
        if "TZID=" in key:
            current["TZID"] = key.split("TZID=", maxsplit=1)[1].split(";", maxsplit=1)[0]
    return events


def unfold_ics_lines(content: str) -> list[str]:
    unfolded: list[str] = []
    for raw_line in content.replace("\r\n", "\n").split("\n"):
        if raw_line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw_line[1:]
        elif raw_line:
            unfolded.append(raw_line)
    return unfolded


def clean_ics_text(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").strip()


def first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def first_string(mapping: dict[str, Any], *keys: str) -> str | None:
    value = first_value(mapping, *keys)
    if value is None:
        return None
    if isinstance(value, dict):
        return first_string(value, "name", "text", "url")
    if isinstance(value, list):
        for item in value:
            text = first_string({"value": item}, "value")
            if text:
                return text
        return None
    text = normalize_space(str(value))
    return text or None


def address_from_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return normalize_space(value)
    if isinstance(value, dict):
        parts = [
            first_string(value, "streetAddress"),
            first_string(value, "addressLocality"),
            first_string(value, "addressRegion"),
            first_string(value, "postalCode"),
            first_string(value, "addressCountry"),
        ]
        return normalize_space(", ".join(part for part in parts if part)) or None
    return normalize_space(str(value))


def location_from_text(text: str) -> list[str]:
    lowered = text.lower()
    if any(token in lowered for token in ("virtual", "online", "webinar", "zoom")):
        return ["Virtual"]
    return []


def location_type_from_text(text: str) -> EventLocationType:
    lowered = text.lower()
    is_virtual = any(token in lowered for token in ("virtual", "online", "webinar", "zoom", "teams meeting"))
    is_in_person = any(token in lowered for token in ("in-person", "in person", "campus", "office", "career fair"))
    if is_virtual and is_in_person:
        return "hybrid"
    if is_virtual:
        return "virtual"
    if is_in_person:
        return "in_person"
    return "unknown"


def event_type_from_text(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    labels = {
        "career_fair": ("career fair", "job fair"),
        "info_session": ("info session", "information session"),
        "webinar": ("webinar",),
        "workshop": ("workshop", "bootcamp"),
        "networking": ("networking", "meet and greet"),
        "conference": ("conference", "summit"),
    }
    for label, tokens in labels.items():
        if any(token in text for token in tokens):
            return label
    return "recruiting"


def event_type_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "recruiting"


def audience_tags_from_text(text: str) -> list[str]:
    lowered = text.lower()
    tags = []
    for tag, tokens in {
        "students": ("student", "students", "campus", "university"),
        "interns": ("intern", "internship"),
        "new_grads": ("new grad", "graduate", "early career"),
        "mba": ("mba",),
        "phd": ("phd", "ph.d"),
        "engineers": ("engineer", "technical", "software"),
    }.items():
        if any(token in lowered for token in tokens):
            tags.append(tag)
    return tags


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull recruiting events from explicit company event pages.")
    parser.add_argument("-i", "--input-file", type=Path, help="JSON array of event source configs.")
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--print-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    sources = read_source_file(args.input_file) if args.input_file else DEFAULT_EVENT_SOURCES
    result = extract_event_sources(sources, timeout_seconds=args.timeout, workers=args.workers)
    output_path = args.output or default_output_path()
    write_result(result, output_path)
    summary = {
        "output_path": str(output_path),
        "source_count": result.source_count,
        "successful_source_count": result.successful_source_count,
        "failed_source_count": result.failed_source_count,
        "event_count": result.event_count,
    }
    print(json.dumps(summary, indent=2))
    if args.print_json:
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
