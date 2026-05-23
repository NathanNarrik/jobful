from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.models import (
    EventLocationType,
    EventPullFailure,
    EventPullResult,
    EventPullSourceResult,
    EventSourceConfig,
    EventSourceStatus,
    FirmKind,
    RecruitingEventListing,
)
from app.events.sources import CANDIDATE_EVENT_SOURCES, DEFAULT_EVENT_SOURCES


DEFAULT_OUTPUT_DIR = Path("outputs")
EVENT_SCHEMA_TYPES = {"Event", "BusinessEvent", "EducationEvent"}
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,text/calendar,*/*",
    "User-Agent": "JobfulEvents/1.0",
}
JSON_HEADERS = {"Accept": "application/json,*/*", "User-Agent": "JobfulEvents/1.0"}
MAJOR_TECH_FIRM_ALIASES: dict[str, tuple[FirmKind, tuple[str, ...]]] = {
    "Amazon": ("technology", ("amazon", "aws", "amazon web services", "amazon student programs")),
    "Meta": ("technology", ("meta", "facebook", "meta university", "meta careers")),
    "Apple": ("technology", ("apple", "careers at apple", "apple retail")),
    "Microsoft": ("technology", ("microsoft",)),
    "Google": ("technology", ("google", "google careers", "careers onair")),
    "NVIDIA": ("technology", ("nvidia",)),
    "Stripe": ("technology", ("stripe",)),
    "Databricks": ("technology", ("databricks",)),
    "Roblox": ("technology", ("roblox",)),
    "Uber": ("technology", ("uber",)),
    "Airbnb": ("technology", ("airbnb",)),
    "Netflix": ("technology", ("netflix",)),
    "Salesforce": ("technology", ("salesforce",)),
    "Adobe": ("technology", ("adobe",)),
    "IBM": ("technology", ("ibm",)),
    "Oracle": ("technology", ("oracle",)),
    "Bloomberg": ("finance", ("bloomberg",)),
    "Palantir": ("technology", ("palantir",)),
}


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
        status: EventSourceStatus = "productive" if events else "empty"
        return events, None, EventPullSourceResult(
            source_url=str(source.event_page_url),
            firm_name=source.firm_name,
            firm_kind=source.firm_kind,
            source_provider=source.source_provider,
            source_scope=source.source_scope,
            status=status,
            event_count=len(events),
        )
    except Exception as exc:
        status = classify_source_exception(source, exc)
        if status != "failed":
            return [], None, EventPullSourceResult(
                source_url=str(source.event_page_url),
                firm_name=source.firm_name,
                firm_kind=source.firm_kind,
                source_provider=source.source_provider,
                source_scope=source.source_scope,
                status=status,
                event_count=0,
                error_type=exc.__class__.__name__,
                message=str(exc),
            )
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
            source_scope=source.source_scope,
            status=status,
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
        provider_events = self._extract_provider_events()
        if provider_events:
            return self._dedupe(provider_events)

        response = self.session.get(
            str(self.source.event_page_url),
            headers=DEFAULT_HEADERS,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/calendar" in content_type or str(self.source.event_page_url).lower().endswith(".ics"):
            return self._dedupe(self._extract_ics(response.text, str(self.source.event_page_url)))

        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        decoded_soup = self._decoded_soup(html)
        events = []
        events.extend(self._extract_json_ld(soup))
        events.extend(self._extract_linked_calendars(soup))
        events.extend(self._extract_embedded_json(soup))
        events.extend(self._extract_google_event_cards(decoded_soup))
        events.extend(self._extract_nasa_event_cards(soup))
        events.extend(self._extract_public_recruiting_cards(soup))
        events.extend(self._extract_html_event_cards(soup))
        return self._dedupe(events)

    def _extract_provider_events(self) -> list[RecruitingEventListing]:
        hostname = urlparse(str(self.source.event_page_url)).hostname or ""
        provider = self.source.source_provider
        if provider == "morgan_stanley_events" or "morganstanley.com" in hostname:
            return self._extract_morgan_stanley_events()
        if provider == "nvidia_university_events" or "nvidia.com" in hostname:
            return self._extract_nvidia_university_events()
        if provider == "eightfold_events" or "eightfold.ai" in hostname or hostname.startswith("jobs."):
            events = self._extract_eightfold_events()
            if events:
                return events
        if provider == "amazon_hiring_events" or "hiring.amazon.com" in hostname:
            events = self._extract_amazon_hiring_events()
            if events:
                return events
        if provider == "jpmorgan_events" or "jpmorganchase.com" in hostname:
            return self._extract_jpmorgan_events()
        return []

    def _extract_jpmorgan_events(self) -> list[RecruitingEventListing]:
        url = "https://www.jpmorganchase.com/services/json/v1/careers/gate/events.json"
        response = self.session.get(
            url,
            headers=JSON_HEADERS,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        events: list[RecruitingEventListing] = []
        for item in payload.get("events", []):
            if not isinstance(item, dict):
                continue
            starts_at = parse_date_and_time(item.get("date_start"), item.get("start_time"))
            if starts_at is None:
                continue
            ends_at = parse_date_and_time(item.get("date_end"), item.get("end_time"))
            title = first_string(item, "event_name")
            if not title:
                continue
            event_url = first_string(item, "event_url", "apply_url", "registration_url") or str(self.source.event_page_url)
            location = [part for part in [first_string(item, "city"), first_string(item, "state"), first_string(item, "country")] if part]
            description = html_to_text(first_string(item, "external_description") or "")
            classification = first_string(item, "event_classification") or "recruiting"
            events.append(
                self._build_event(
                    event_title=title,
                    event_url=event_url,
                    registration_url=event_url,
                    source_event_id=first_string(item, "event_id", "id")
                    or "|".join(
                        part
                        for part in [
                            title,
                            first_string(item, "date_start"),
                            first_string(item, "start_time"),
                            first_string(item, "city"),
                        ]
                        if part
                    ),
                    event_type=event_type_from_text(classification, title),
                    audience_tags=audience_tags_from_text(f"{title} {description}"),
                    location=location,
                    location_type=location_type_from_text(" ".join(location) or title),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    timezone=first_string(item, "time_zone", "timezone"),
                    description=description,
                    raw_payload=item,
                )
            )
        return events

    def _extract_morgan_stanley_events(self) -> list[RecruitingEventListing]:
        url = "https://www.morganstanley.com/web/career_services/webapp/service/careerservice/eventdetails.json?category=sg"
        response = self.session.get(url, headers=JSON_HEADERS, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("eventResults", []) if isinstance(payload, dict) else []
        events: list[RecruitingEventListing] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = first_string(item, "eventTitle", "title", "name")
            starts_at = parse_date_and_time(item.get("eventStartDate"), item.get("eventTime"))
            if not title or starts_at is None:
                continue
            ends_at = parse_date_and_time(item.get("eventEndDate"), item.get("eventTime"))
            description = html_to_text(first_string(item, "eventHtmlDescription", "eventDescription", "description") or "")
            event_url = first_string(item, "eventDetailUrl", "eventUrl", "url") or str(self.source.event_page_url)
            location = self._string_list(first_string(item, "eventCity", "eventLocation", "eventCountry"))
            if not location:
                location = [part for part in [first_string(item, "eventCity"), first_string(item, "eventState"), first_string(item, "eventCountry")] if part]
            events.append(
                self._build_event(
                    event_title=title,
                    event_url=urljoin(str(self.source.event_page_url), event_url),
                    registration_url=urljoin(str(self.source.event_page_url), event_url),
                    source_event_id=first_string(item, "eventId", "id"),
                    event_type=event_type_from_text(first_string(item, "eventType", "eventCategory") or title, description),
                    audience_tags=audience_tags_from_text(f"{title} {description}"),
                    location=location,
                    location_type=location_type_from_text(" ".join(location) or title),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    timezone=first_string(item, "eventTimezone", "timezone"),
                    description=description,
                    raw_payload=item,
                )
            )
        return events

    def _extract_nvidia_university_events(self) -> list[RecruitingEventListing]:
        url = "https://www.nvidia.com/content/dam/en-zz/Solutions/university-events-calendar/en-us.json"
        response = self.session.get(url, headers=JSON_HEADERS, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        items = payload if isinstance(payload, list) else payload.get("events", []) if isinstance(payload, dict) else []
        events: list[RecruitingEventListing] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = first_string(item, "title", "name")
            starts_at = self._parse_datetime(first_value(item, "startDate", "start_date", "date"))
            if not title or starts_at is None:
                continue
            event_url = first_string(item, "url", "link") or str(self.source.event_page_url)
            description = normalize_space(
                " ".join(
                    part
                    for part in [
                        first_string(item, "description", "summary"),
                        first_string(item, "venue"),
                        first_string(item, "booth"),
                    ]
                    if part
                )
            )
            location = self._string_list(first_string(item, "location", "venue"))
            events.append(
                self._build_event(
                    event_title=title,
                    event_url=urljoin(str(self.source.event_page_url), event_url),
                    registration_url=urljoin(str(self.source.event_page_url), event_url),
                    source_event_id=first_string(item, "id", "eventId") or f"{title}|{starts_at.isoformat()}",
                    event_type=event_type_from_text(title, description),
                    audience_tags=audience_tags_from_text(f"{title} {description} university student campus"),
                    location=location,
                    location_type=location_type_from_text(" ".join(location) or title),
                    starts_at=starts_at,
                    ends_at=self._parse_datetime(first_value(item, "endDate", "end_date")),
                    timezone=first_string(item, "timezone", "timeZone"),
                    description=description or None,
                    raw_payload=item,
                )
            )
        return events

    def _extract_eightfold_events(self) -> list[RecruitingEventListing]:
        response = self.session.get(str(self.source.event_page_url), headers=DEFAULT_HEADERS, timeout=self.timeout_seconds)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        events: list[RecruitingEventListing] = []
        for item in self._walk_script_json(soup):
            event_data = item.get("eventData") if isinstance(item.get("eventData"), dict) else item
            if not isinstance(event_data, dict):
                continue
            if not first_string(event_data, "plannedEventEncId", "eventLandingURL", "name"):
                continue
            event = self._event_from_eightfold_mapping(event_data)
            if event is not None:
                events.append(event)
        return events

    def _extract_amazon_hiring_events(self) -> list[RecruitingEventListing]:
        response = self.session.get(str(self.source.event_page_url), headers=DEFAULT_HEADERS, timeout=self.timeout_seconds)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        events = []
        for item in self._walk_script_json(soup):
            if self._looks_like_event(item) or first_string(item, "eventName", "title", "name"):
                event = self._event_from_mapping(item, fallback_url=str(self.source.event_page_url))
                if event is not None and "amazon" in f"{event.event_title} {event.description or ''}".lower():
                    events.append(event)
        events.extend(self._extract_public_recruiting_cards(soup))
        return events

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
                    headers={"Accept": "text/calendar,*/*", "User-Agent": DEFAULT_HEADERS["User-Agent"]},
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                events.extend(self._extract_ics(response.text, url))
            except requests.RequestException:
                continue
        return events

    def _extract_embedded_json(self, soup: BeautifulSoup) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        for item in self._walk_script_json(soup):
            if self._looks_like_event(item):
                event = self._event_from_mapping(item, fallback_url=str(self.source.event_page_url))
                if event is not None:
                    events.append(event)
        return events

    def _extract_public_recruiting_cards(self, soup: BeautifulSoup) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        selectors = [
            "[class*=event]",
            "[id*=event]",
            "article",
            "li",
            "tr",
        ]
        for selector in selectors:
            for element in soup.select(selector):
                text = normalize_space(element.get_text(" ", strip=True))
                if len(text) < 20 or not self._contains_event_language(text):
                    continue
                firm_match = self._firm_match(text)
                if firm_match is None:
                    continue
                firm_name, firm_kind = firm_match
                starts_at = self._parse_element_datetime(element, text)
                if starts_at is None:
                    continue
                title = self._title_from_element(element, fallback=text)
                link = element.find("a", href=True)
                event_url = urljoin(str(self.source.event_page_url), str(link["href"])) if link else str(self.source.event_page_url)
                events.append(
                    self._build_event(
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
                        firm_name=firm_name,
                        firm_kind=firm_kind,
                    )
                )
        return self._dedupe(events)[:100]

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

    def _extract_google_event_cards(self, soup: BeautifulSoup) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        for element in soup.select('[data-cy="resultsList"]'):
            title = normalize_space(str(element.get("data-tracking-title") or ""))
            link = element.find("a", href=True)
            if not title or link is None:
                continue
            text = normalize_space(element.get_text(" ", strip=True))
            event_url = urljoin(str(self.source.event_page_url), str(link["href"]))
            location_text = first_matching_text(text, ("VIRTUAL", "ONLINE", "ONSITE", "VARIES")) or ""
            event_type = element.get("data-glue-filter-event-type") or event_type_from_text(title, text)
            extracted_at = datetime.now(UTC)
            events.append(
                self._build_event(
                    event_title=title,
                    event_url=event_url,
                    registration_url=event_url,
                    source_event_id=event_url,
                    event_type=str(event_type),
                    audience_tags=audience_tags_from_text(text),
                    location=location_from_text(location_text or text),
                    location_type=location_type_from_text(location_text or text),
                    starts_at=extracted_at,
                    ends_at=extracted_at + timedelta(days=365),
                    timezone=None,
                    description=text,
                    raw_payload={
                        "tracking_title": title,
                        "event_type": element.get("data-glue-filter-event-type"),
                        "location": element.get("data-glue-filter-location"),
                        "topic": element.get("data-glue-filter-topic"),
                    },
                )
            )
        return events

    def _extract_nasa_event_cards(self, soup: BeautifulSoup) -> list[RecruitingEventListing]:
        events: list[RecruitingEventListing] = []
        for element in soup.select("a.hds-event-item[href]"):
            title_element = element.select_one(".hds-event-title")
            date_element = element.select_one("[data-event-start-date]")
            if title_element is None or date_element is None:
                continue
            title = normalize_space(title_element.get_text(" ", strip=True))
            starts_at = self._parse_datetime(date_element.get("data-event-start-date"))
            if not title or starts_at is None:
                continue
            type_element = element.select_one(".hds-event-type")
            location_element = element.select_one(".hds-event-short-location")
            event_type = normalize_space(type_element.get_text(" ", strip=True)) if type_element else "event"
            location = self._string_list(location_element.get_text(" ", strip=True) if location_element else "")
            event_url = urljoin(str(self.source.event_page_url), str(element["href"]))
            events.append(
                self._build_event(
                    event_title=title,
                    event_url=event_url,
                    registration_url=event_url,
                    source_event_id=str(element.get("event-id") or event_url),
                    event_type=event_type,
                    audience_tags=audience_tags_from_text(f"{title} {event_type}"),
                    location=location,
                    location_type=location_type_from_text(" ".join(location) or event_type),
                    starts_at=starts_at,
                    ends_at=self._parse_timestamp(date_element.get("data-event-timestamp-end")),
                    timezone=None,
                    description=normalize_space(element.get_text(" ", strip=True)),
                    raw_payload={
                        "event_id": element.get("event-id"),
                        "display_date": normalize_space(date_element.get_text(" ", strip=True)),
                        "event_type": event_type,
                    },
                )
            )
        return events

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
        title = first_string(item, "name", "title", "headline", "summary", "eventName")
        starts_at = self._parse_datetime(
            first_value(item, "startDate", "start_date", "startsAt", "startTime", "startTimestamp", "start_timestamp", "date")
        )
        if not title or starts_at is None:
            return None
        event_url = first_string(item, "url", "eventUrl", "canonicalUrl", "link") or fallback_url
        registration_url = first_string(item, "registrationUrl", "registration_url", "applyUrl", "rsvpUrl", "eventLandingURL") or event_url
        location = self._location_from_mapping(item)
        description = first_string(item, "description", "body", "shortDescription", "details")
        event_type = first_string(item, "eventType", "event_type", "category", "type") or event_type_from_text(title, description or "")
        source_event_id = first_string(item, "identifier", "id", "uid", "eventId")
        firm_match = self._firm_match(f"{title} {description or ''}")
        firm_name = firm_match[0] if firm_match and self.source.source_scope in {"university_calendar", "handshake_public", "candidate"} else None
        firm_kind = firm_match[1] if firm_match and self.source.source_scope in {"university_calendar", "handshake_public", "candidate"} else None
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
            ends_at=self._parse_datetime(first_value(item, "endDate", "end_date", "endsAt", "endTime", "endTimestamp", "end_timestamp")),
            timezone=first_string(item, "timezone", "timeZone", "tz"),
            description=description,
            raw_payload=item,
            firm_name=firm_name,
            firm_kind=firm_kind,
        )

    def _event_from_eightfold_mapping(self, item: dict[str, Any]) -> RecruitingEventListing | None:
        title = first_string(item, "name", "title")
        starts_at = self._parse_datetime(first_value(item, "startTimestamp", "start_timestamp", "startDate"))
        if not title or starts_at is None:
            return None
        event_url = first_string(item, "eventLandingURL", "registrationUrl", "url") or str(self.source.event_page_url)
        description = html_to_text(first_string(item, "description") or "")
        location_text = first_string(item, "completeVenue", "venue", "address", "institution") or ""
        location = self._string_list(location_text)
        location_type = "virtual" if first_string(item, "eventLocationType") == "virtual_event" else location_type_from_text(location_text or description or title)
        return self._build_event(
            event_title=title,
            event_url=event_url,
            registration_url=event_url,
            source_event_id=first_string(item, "plannedEventEncId", "id"),
            event_type=event_type_from_text(first_string(item, "eventCategory") or title, description),
            audience_tags=audience_tags_from_text(f"{title} {description}"),
            location=location,
            location_type=location_type,
            starts_at=starts_at,
            ends_at=self._parse_datetime(first_value(item, "endTimestamp", "end_timestamp", "endDate")),
            timezone=first_string(item, "selectedTimezone", "timezone"),
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
        firm_name: str | None = None,
        firm_kind: FirmKind | None = None,
    ) -> RecruitingEventListing:
        normalized_location = location or ["Virtual"] if location_type == "virtual" else location or ["Unspecified"]
        return RecruitingEventListing(
            firm_name=firm_name or self.source.firm_name,
            firm_kind=firm_kind or self.source.firm_kind,
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

    def _walk_script_json(self, soup: BeautifulSoup) -> Iterable[dict[str, Any]]:
        for script in soup.find_all("script"):
            text = script.string or script.get_text(" ", strip=True)
            stripped = text.strip()
            if not stripped:
                continue
            payload = None
            if stripped[0] in "[{":
                payload = self._loads_json(stripped)
            if payload is None and "eventData" in stripped:
                payload = self._loads_json_object_named(stripped, "eventData")
            if payload is None:
                continue
            yield from self._walk_json(payload)

    def _loads_json_object_named(self, text: str, name: str) -> Any | None:
        marker = f'"{name}"'
        start = text.find(marker)
        if start < 0:
            marker = name
            start = text.find(marker)
        if start < 0:
            return None
        brace_start = text.find("{", start)
        if brace_start < 0:
            return None
        depth = 0
        in_string = False
        escape = False
        for index in range(brace_start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return self._loads_json(text[brace_start : index + 1])
        return None

    def _firm_match(self, text: str) -> tuple[str, FirmKind] | None:
        lowered = text.lower()
        source_aliases = tuple(alias.lower() for alias in self.source.firm_aliases)
        if source_aliases and any(alias in lowered for alias in source_aliases):
            return self.source.firm_name, self.source.firm_kind
        for firm_name, (firm_kind, aliases) in MAJOR_TECH_FIRM_ALIASES.items():
            if any(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered) for alias in aliases):
                return firm_name, firm_kind
        return None

    def _parse_element_datetime(self, element: Any, text: str) -> datetime | None:
        time_element = element.find("time") if hasattr(element, "find") else None
        parsed = self._parse_datetime(time_element.get("datetime") if time_element else None)
        if parsed is not None:
            return parsed
        return self._parse_datetime(text)

    def _title_from_element(self, element: Any, *, fallback: str) -> str:
        heading = element.find(["h1", "h2", "h3", "h4", "strong"]) if hasattr(element, "find") else None
        title = normalize_space(heading.get_text(" ", strip=True)) if heading else ""
        if title:
            return title[:180]
        cells = element.find_all(["td", "th"], limit=3) if hasattr(element, "find_all") else []
        for cell in cells:
            cell_text = normalize_space(cell.get_text(" ", strip=True))
            if cell_text and not self._parse_datetime(cell_text):
                return cell_text[:180]
        return fallback[:180]

    def _location_from_mapping(self, item: dict[str, Any]) -> list[str]:
        value = first_value(item, "location", "eventLocation", "venue", "completeVenue", "address")
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
        has_title = any(key in item for key in ("name", "title", "headline", "summary", "eventName"))
        has_date = any(key in item for key in ("startDate", "start_date", "startsAt", "startTime", "startTimestamp", "start_timestamp", "date"))
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
        date_match = re.search(
            r"((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+)?"
            r"([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4}|\d{1,2}\s+[A-Z][a-z]+\.?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})",
            text,
        )
        time_matches = list(re.finditer(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|AM|PM|am|pm)\b", text))
        if date_match:
            parsed = parse_date_and_time(date_match.group(0), time_matches[0].group(0) if time_matches else None)
            if parsed is not None:
                return parsed
        for date_format in ("%A, %B %d, %Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%Y%m%d"):
            try:
                return datetime.strptime(text, date_format).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None

    def _parse_timestamp(self, value: object) -> datetime | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return datetime.fromtimestamp(float(str(value)), UTC)
        except ValueError:
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

    def _decoded_soup(self, text: str) -> BeautifulSoup:
        decoded = (
            text.replace(r"\u003c", "<")
            .replace(r"\u003e", ">")
            .replace(r"\u003d", "=")
            .replace(r"\u0026", "&")
            .replace(r"\"", '"')
            .replace(r"\/", "/")
        )
        decoded = html.unescape(decoded)
        return BeautifulSoup(decoded, "html.parser")

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


def classify_source_exception(source: EventSourceConfig, exc: Exception) -> EventSourceStatus:
    hostname = urlparse(str(source.event_page_url)).hostname or ""
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if "joinhandshake.com" in hostname and status_code in {401, 403}:
        return "auth-required"
    if status_code == 401:
        return "auth-required"
    if status_code in {403, 429}:
        return "blocked"
    if status_code == 404:
        return "inactive"
    return "failed"


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


def parse_date_and_time(date_value: object, time_value: object = None) -> datetime | None:
    if not date_value:
        return None
    date_text = normalize_space(str(date_value))
    time_text = normalize_space(str(time_value or "12:00 AM"))
    date_text = re.sub(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+", "", date_text)
    date_text = date_text.replace(".", "")
    time_text = re.sub(r"\b(GMT|UTC|ET|EST|EDT|CT|CST|CDT|PT|PST|PDT)\b", "", time_text, flags=re.IGNORECASE)
    time_text = normalize_space(time_text.replace(".", ""))
    for date_format in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            parsed_date = datetime.strptime(date_text, date_format)
            break
        except ValueError:
            parsed_date = None
    if parsed_date is None:
        return None
    for time_format in ("%I:%M %p", "%H:%M", "%I %p", "%I%p"):
        try:
            parsed_time = datetime.strptime(time_text.upper(), time_format).time()
            return datetime.combine(parsed_date.date(), parsed_time, tzinfo=UTC)
        except ValueError:
            continue
    return parsed_date.replace(tzinfo=UTC)


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


def html_to_text(value: str) -> str:
    if not value:
        return ""
    return normalize_space(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


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
    if any(token in lowered for token in ("onsite", "on-site", "in-person", "in person")):
        return ["In person"]
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


def first_matching_text(text: str, options: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for option in options:
        if option.lower() in lowered:
            return option
    return None


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
    parser.add_argument("--include-candidates", action="store_true", help="Also pull broader candidate sources that may be empty or auth-gated.")
    parser.add_argument("--print-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    sources = read_source_file(args.input_file) if args.input_file else DEFAULT_EVENT_SOURCES
    if args.include_candidates and not args.input_file:
        sources = [*sources, *CANDIDATE_EVENT_SOURCES]
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
