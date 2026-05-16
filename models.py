from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_serializer


AtsProvider = Literal[
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "amazon",
    "google",
    "apple",
    "oracle",
    "talentbrew",
    "avature",
]


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


ProgramType = Literal["internship", "new_grad", "experienced", "other"]
RemoteType = Literal["remote", "hybrid", "onsite", "unknown"]
NormalizationStatus = Literal["COMPLETE", "NEEDS_REVIEW", "FAILED"]
VisaStatus = Literal[
    "sponsors",
    "does_not_sponsor",
    "requires_authorization",
    "opt_cpt_allowed",
    "not_mentioned",
    "unclear",
]
AcademicLevel = Literal[
    "freshman",
    "sophomore",
    "junior",
    "senior",
    "undergraduate",
    "masters",
    "phd",
    "new_grad",
]


class JobNormalization(BaseModel):
    """AI/heuristic eligibility metadata extracted from a raw job listing."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    program_type: ProgramType
    academic_levels: list[AcademicLevel] = Field(default_factory=list)
    degree_requirements: list[str] = Field(default_factory=list)
    required_grad_years: list[int] = Field(default_factory=list)
    visa_sponsorship: bool | None = None
    visa_status: VisaStatus = "not_mentioned"
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    min_gpa: float | None = None
    clearance_required: bool = False
    remote_type: RemoteType = "unknown"
    normalization_status: NormalizationStatus
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    review_reasons: list[str] = Field(default_factory=list)


class NormalizedJobRecord(BaseModel):
    """A Phase 1 listing plus Phase 3 normalized metadata."""

    model_config = ConfigDict(extra="forbid")

    job: JobListing
    cleaned_description: str
    normalization: JobNormalization
    normalization_method: Literal["heuristic", "ollama", "fallback"]
    normalized_at: datetime


class NormalizationResult(BaseModel):
    """Serializable artifact for one Phase 3 normalization run."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    source_job_count: int
    normalized_job_count: int
    duplicate_job_count: int
    status_counts: dict[str, int]
    records: list[NormalizedJobRecord]
