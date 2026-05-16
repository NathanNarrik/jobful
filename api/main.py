from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_db
from api.routes.companies import router as companies_router
from api.routes.jobs import router as jobs_router
from api.routes.stats import router as stats_router
from api.schemas import HealthResponse


app = FastAPI(title="Jobful API", version="0.4.0")
app.include_router(jobs_router)
app.include_router(companies_router)
app.include_router(stats_router)


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok")
