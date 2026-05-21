from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.events.db.config import events_database_url


def create_events_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    selected_url = url or events_database_url()
    connect_args = {"check_same_thread": False} if selected_url.startswith("sqlite") else {}
    return create_engine(selected_url, echo=echo, future=True, connect_args=connect_args)
