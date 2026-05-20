from __future__ import annotations

import os


DEFAULT_EVENTS_DATABASE_URL = "postgresql+psycopg://jobful_events:jobful_events_dev@localhost:5433/jobful_events"


def events_database_url() -> str:
    return os.getenv("JOBFUL_EVENTS_DATABASE_URL", DEFAULT_EVENTS_DATABASE_URL)
