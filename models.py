from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_serializer


AtsProvider = Literal["greenhouse", "lever", "ashby", "workday", "amazon", "google", "oracle"]


class JobListing(BaseModel):
    """Normalized active job listing emitted by every ATS extractor."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company_name: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    job_url: HttpUrl
    ats_provider: AtsProvider
    ats_job_id: str = Field(min_length=1)
    location: list[str]
    raw_description: str
    description_html: str | None = None
    employment_type: str | None = None
    departments: list[str] = Field(default_factory=list)
    date_posted: datetime | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    extracted_at: datetime

    @field_serializer("job_url")
    def serialize_job_url(self, job_url: HttpUrl) -> str:
        return str(job_url)


class PullFailure(BaseModel):
    """A source URL that could not be extracted during a batch pull."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_url: str
    ats_provider: str | None = None
    board_token: str | None = None
    error_type: str
    message: str


class PullSourceResult(BaseModel):
    """Per-source extraction metadata for analysis and auditing."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_url: str
    ats_provider: str | None = None
    board_token: str | None = None
    status: Literal["success", "failed"]
    job_count: int
    error_type: str | None = None
    message: str | None = None


class PullResult(BaseModel):
    """Serializable artifact for one Jobful extraction run."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    source_count: int
    successful_source_count: int
    failed_source_count: int
    job_count: int
    sources: list[PullSourceResult]
    jobs: list[JobListing]
    failures: list[PullFailure]
