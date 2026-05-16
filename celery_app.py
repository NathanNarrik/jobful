from __future__ import annotations

import os

from celery import Celery


REDIS_URL = os.getenv("JOBFUL_REDIS_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("JOBFUL_CELERY_RESULT_BACKEND", REDIS_URL)

celery_app = Celery(
    "jobful",
    broker=REDIS_URL,
    backend=RESULT_BACKEND,
    include=["tasks"],
)

celery_app.config_from_object("celeryconfig")
