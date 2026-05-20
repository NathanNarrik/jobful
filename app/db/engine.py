from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.db.config import database_url


def create_jobful_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    connect_args = {"check_same_thread": False} if (url or database_url()).startswith("sqlite") else {}
    return create_engine(url or database_url(), echo=echo, future=True, connect_args=connect_args)
