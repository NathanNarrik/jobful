from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_events_db
from app.api.schemas import EventDetail, EventListItem, EventSourceSummary, PaginatedEventsResponse
from app.events.db.models import EventSource, RecruitingEvent


router = APIRouter(tags=["events"])


@router.get("/events", response_model=PaginatedEventsResponse)
def list_events(
    db: Session = Depends(get_events_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = None,
    firm: str | None = None,
    firm_kind: str | None = None,
    event_type: str | None = None,
    location_type: str | None = None,
    starts_after: datetime | None = None,
    starts_before: datetime | None = None,
    active_only: bool = True,
) -> PaginatedEventsResponse:
    stmt = select(RecruitingEvent)
    count_stmt = select(func.count()).select_from(RecruitingEvent)
    filters = build_event_filters(
        search=search,
        firm=firm,
        firm_kind=firm_kind,
        event_type=event_type,
        location_type=location_type,
        starts_after=starts_after,
        starts_before=starts_before,
        active_only=active_only,
    )
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int(db.execute(count_stmt).scalar_one())
    events = db.execute(
        stmt.order_by(RecruitingEvent.starts_at.asc(), RecruitingEvent.last_seen_at.desc(), RecruitingEvent.id.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    return PaginatedEventsResponse(
        items=[EventListItem.model_validate(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/events/{event_id}", response_model=EventDetail)
def get_event(event_id: UUID, db: Session = Depends(get_events_db)) -> EventDetail:
    event = db.get(RecruitingEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventDetail.model_validate(event)


@router.get("/event-sources", response_model=list[EventSourceSummary])
def list_event_sources(db: Session = Depends(get_events_db)) -> list[EventSourceSummary]:
    rows = db.execute(
        select(
            EventSource,
            func.count(RecruitingEvent.id).label("event_count"),
            func.count(RecruitingEvent.id).filter(RecruitingEvent.is_active.is_(True)).label("active_event_count"),
        )
        .outerjoin(RecruitingEvent, RecruitingEvent.source_id == EventSource.id)
        .group_by(EventSource.id)
        .order_by(EventSource.firm_name.asc())
    ).all()
    return [
        EventSourceSummary.model_validate(
            {
                **{column.name: getattr(source, column.name) for column in source.__table__.columns},
                "event_count": int(event_count),
                "active_event_count": int(active_event_count),
            }
        )
        for source, event_count, active_event_count in rows
    ]


def build_event_filters(
    *,
    search: str | None,
    firm: str | None,
    firm_kind: str | None,
    event_type: str | None,
    location_type: str | None,
    starts_after: datetime | None,
    starts_before: datetime | None,
    active_only: bool,
) -> list[object]:
    filters: list[object] = []
    if active_only:
        filters.append(RecruitingEvent.is_active.is_(True))
    if firm:
        filters.append(RecruitingEvent.firm_name.ilike(f"%{firm.strip()}%"))
    if firm_kind:
        filters.append(RecruitingEvent.firm_kind == firm_kind)
    if event_type:
        filters.append(RecruitingEvent.event_type == event_type)
    if location_type:
        filters.append(RecruitingEvent.location_type == location_type)
    if starts_after:
        filters.append(RecruitingEvent.starts_at >= starts_after)
    if starts_before:
        filters.append(RecruitingEvent.starts_at <= starts_before)
    if search:
        token = f"%{search.strip()}%"
        filters.append(
            or_(
                RecruitingEvent.event_title.ilike(token),
                RecruitingEvent.firm_name.ilike(token),
                RecruitingEvent.description.ilike(token),
                cast(RecruitingEvent.location, String).ilike(token),
            )
        )
    return filters
