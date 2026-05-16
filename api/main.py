from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_db
from api.routes.applications import router as applications_router
from api.routes.companies import router as companies_router
from api.routes.jobs import router as jobs_router
from api.routes.stats import router as stats_router
from api.schemas import HealthResponse


app = FastAPI(title="Jobful API", version="0.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(jobs_router)
app.include_router(companies_router)
app.include_router(stats_router)
app.include_router(applications_router)


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok")
