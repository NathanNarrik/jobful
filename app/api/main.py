from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps import get_events_db
from app.api.routes.applications import router as applications_router
from app.api.routes.companies import router as companies_router
from app.api.routes.events import router as events_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.stats import router as stats_router
from app.api.schemas import HealthResponse


app = FastAPI(title="Jobful API", version="0.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(jobs_router)
app.include_router(events_router)
app.include_router(companies_router)
app.include_router(stats_router)
app.include_router(applications_router)


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db), events_db: Session = Depends(get_events_db)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    events_status = "ok"
    try:
        events_db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        events_status = "unavailable"
    return HealthResponse(status="ok", database="ok", events_database=events_status)
