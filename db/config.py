from __future__ import annotations

import os


DEFAULT_DATABASE_URL = "postgresql+psycopg://jobful:jobful_dev@localhost:5432/jobful"
DEFAULT_ASYNC_DATABASE_URL = "postgresql+asyncpg://jobful:jobful_dev@localhost:5432/jobful"


def database_url() -> str:
    return os.getenv("JOBFUL_DATABASE_URL", DEFAULT_DATABASE_URL)


def async_database_url() -> str:
    return os.getenv("JOBFUL_ASYNC_DATABASE_URL", DEFAULT_ASYNC_DATABASE_URL)
