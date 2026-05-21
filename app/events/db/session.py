from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.events.db.engine import create_events_engine


events_engine = create_events_engine()
EventsSessionLocal = sessionmaker(bind=events_engine, autoflush=False, expire_on_commit=False, future=True)


def get_events_session() -> Iterator[Session]:
    with EventsSessionLocal() as session:
        yield session
