from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import utc_now
from app.events.db.engine import create_events_engine
from app.events.db.models import EventBase, EventSource, RecruitingEvent
from app.models import EventPullResult, EventSourceConfig, RecruitingEventListing


@dataclass(frozen=True)
class EventImportSummary:
    events_read: int = 0
    sources_inserted: int = 0
    events_inserted: int = 0
    events_updated: int = 0
    skipped: int = 0
    failed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "events_read": self.events_read,
            "sources_inserted": self.sources_inserted,
            "events_inserted": self.events_inserted,
            "events_updated": self.events_updated,
            "skipped": self.skipped,
            "failed": self.failed,
        }


def load_event_pull_result(path: Path) -> EventPullResult:
    return EventPullResult.model_validate_json(path.read_text(encoding="utf-8"))


def import_pull_result(session: Session, result: EventPullResult) -> EventImportSummary:
    source_map: dict[str, EventSource] = {}
    sources_inserted = 0
    for source_result in result.sources:
        source, inserted = upsert_event_source(
            session,
            EventSourceConfig(
                firm_name=source_result.firm_name,
                firm_kind=source_result.firm_kind,
                event_page_url=source_result.source_url,
                source_provider=source_result.source_provider,
                source_scope=source_result.source_scope,
            ),
            status=source_result.status,
            error_type=source_result.error_type,
            error_message=source_result.message,
        )
        source_map[source_result.source_url] = source
        if inserted:
            sources_inserted += 1

    counters = {
        "events_read": len(result.events),
        "sources_inserted": sources_inserted,
        "events_inserted": 0,
        "events_updated": 0,
        "skipped": 0,
        "failed": 0,
    }
    for event in result.events:
        try:
            source = match_source_for_event(source_map, event)
            inserted = upsert_recruiting_event(session, event, source)
            if inserted:
                counters["events_inserted"] += 1
            else:
                counters["events_updated"] += 1
        except Exception:
            counters["failed"] += 1

    session.commit()
    return EventImportSummary(**counters)


def import_events(session: Session, events: list[RecruitingEventListing], source: EventSourceConfig) -> EventImportSummary:
    event_source, sources_inserted = upsert_event_source(session, source, status="productive" if events else "empty")
    inserted = 0
    updated = 0
    failed = 0
    for event in events:
        try:
            if upsert_recruiting_event(session, event, event_source):
                inserted += 1
            else:
                updated += 1
        except Exception:
            failed += 1
    session.commit()
    return EventImportSummary(
        events_read=len(events),
        sources_inserted=1 if sources_inserted else 0,
        events_inserted=inserted,
        events_updated=updated,
        failed=failed,
    )


def upsert_event_source(
    session: Session,
    source: EventSourceConfig,
    *,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
) -> tuple[EventSource, bool]:
    source_url = str(source.event_page_url)
    status = normalize_source_status(status)
    existing = session.execute(select(EventSource).where(EventSource.source_url == source_url)).scalar_one_or_none()
    now = utc_now()
    if existing is not None:
        existing.firm_name = source.firm_name
        existing.firm_kind = source.firm_kind
        existing.source_provider = source.source_provider
        existing.source_scope = source.source_scope
        existing.source_status = status
        existing.is_active = status != "inactive"
        existing.last_scraped_at = now
        if status in {"productive", "empty", "parser-needed"}:
            existing.last_success_at = now
            existing.last_error_type = None
            existing.last_error_message = None
        else:
            existing.last_error_type = error_type
            existing.last_error_message = error_message
        session.flush()
        return existing, False

    event_source = EventSource(
        firm_name=source.firm_name,
        firm_kind=source.firm_kind,
        source_url=source_url,
        source_provider=source.source_provider,
        source_scope=source.source_scope,
        source_status=status,
        is_active=status != "inactive",
        last_scraped_at=now,
        last_success_at=now if status in {"productive", "empty", "parser-needed"} else None,
        last_error_type=error_type,
        last_error_message=error_message,
    )
    session.add(event_source)
    session.flush()
    return event_source, True


def normalize_source_status(status: str) -> str:
    return "productive" if status == "success" else status


def upsert_recruiting_event(session: Session, event: RecruitingEventListing, source: EventSource | None) -> bool:
    values = event_values(event, source)
    existing = session.execute(select(RecruitingEvent).where(RecruitingEvent.content_hash == event.content_hash)).scalar_one_or_none()

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = pg_insert(RecruitingEvent).values(**values)
        update_values = {
            key: stmt.excluded[key]
            for key in values
            if key not in {"id", "content_hash", "first_seen_at"}
        }
        update_values["last_seen_at"] = utc_now()
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[RecruitingEvent.content_hash],
                set_=update_values,
            )
        )
        return existing is None

    if existing is not None:
        for key, value in values.items():
            if key not in {"id", "content_hash", "first_seen_at"}:
                setattr(existing, key, value)
        existing.last_seen_at = utc_now()
        session.flush()
        return False

    session.add(RecruitingEvent(**values))
    session.flush()
    return True


def event_values(event: RecruitingEventListing, source: EventSource | None) -> dict[str, Any]:
    now = utc_now()
    return {
        "source_id": source.id if source else None,
        "firm_name": event.firm_name,
        "firm_kind": event.firm_kind,
        "event_title": event.event_title,
        "event_url": str(event.event_url),
        "registration_url": str(event.registration_url) if event.registration_url else None,
        "source_provider": event.source_provider,
        "source_event_id": event.source_event_id,
        "event_type": event.event_type,
        "audience_tags": event.audience_tags,
        "location": event.location,
        "location_type": event.location_type,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "timezone": event.timezone,
        "description": event.description,
        "raw_payload": event.raw_payload,
        "content_hash": event.content_hash,
        "extracted_at": event.extracted_at,
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": is_event_active(event),
    }


def is_event_active(event: RecruitingEventListing) -> bool:
    now = utc_now()
    if event.ends_at is not None:
        return event.ends_at >= now
    return event.starts_at >= now


def match_source_for_event(source_map: dict[str, EventSource], event: RecruitingEventListing) -> EventSource | None:
    event_url = str(event.event_url)
    registration_url = str(event.registration_url) if event.registration_url else ""
    for source in source_map.values():
        if source.source_url in {event_url, registration_url}:
            return source
    event_host = urlparse(event_url).hostname
    for source in source_map.values():
        source_host = urlparse(source.source_url).hostname
        if (
            source_host
            and event_host == source_host
            and source.firm_name == event.firm_name
            and source.firm_kind == event.firm_kind
        ):
            return source
    for source in source_map.values():
        if source.firm_name == event.firm_name and source.firm_kind == event.firm_kind:
            return source
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a recruiting-event pull artifact into the events database.")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--create-tables", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = create_events_engine(args.database_url)
    if args.create_tables:
        EventBase.metadata.create_all(engine)
    result = load_event_pull_result(args.artifact)
    with Session(engine) as session:
        summary = import_pull_result(session, result)
    print(json.dumps(summary.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
