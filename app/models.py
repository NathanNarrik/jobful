from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_serializer


AtsProvider = Literal[
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "amazon",
    "google",
    "meta",
    "apple",
    "eightfold",
    "oracle",
    "smartrecruiters",
    "successfactors",
    "talentbrew",
    "usajobs",
    "avature",
    "mcloud",
    "verizon",
    "walmart",
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


FirmKind = Literal[
    "technology",
    "finance",
    "consulting",
    "healthcare",
    "government",
    "startup",
    "industrial",
    "retail",
    "other",
]
EventLocationType = Literal["virtual", "in_person", "hybrid", "unknown"]


class RecruitingEventListing(BaseModel):
    """Recruiting event emitted by an event-source extractor."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    firm_name: str = Field(min_length=1)
    firm_kind: FirmKind = "other"
    event_title: str = Field(min_length=1)
    event_url: HttpUrl
    registration_url: HttpUrl | None = None
    source_provider: str = Field(default="company_events", min_length=1)
    source_event_id: str | None = None
    event_type: str = Field(default="recruiting", min_length=1)
    audience_tags: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    location_type: EventLocationType = "unknown"
    starts_at: datetime
    ends_at: datetime | None = None
    timezone: str | None = None
    description: str | None = None
    raw_payload: dict[str, Any] | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    extracted_at: datetime

    @field_serializer("event_url")
    def serialize_event_url(self, event_url: HttpUrl) -> str:
        return str(event_url)

    @field_serializer("registration_url")
    def serialize_registration_url(self, registration_url: HttpUrl | None) -> str | None:
        return str(registration_url) if registration_url is not None else None


class EventSourceConfig(BaseModel):
    """Explicit public event page source used by the event fetcher."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    firm_name: str = Field(min_length=1)
    firm_kind: FirmKind = "other"
    event_page_url: HttpUrl
    source_provider: str = "company_events"

    @field_serializer("event_page_url")
    def serialize_event_page_url(self, event_page_url: HttpUrl) -> str:
        return str(event_page_url)


class EventPullFailure(BaseModel):
    """An event source URL that could not be extracted."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_url: str
    firm_name: str
    firm_kind: str
    source_provider: str
    error_type: str
    message: str


class EventPullSourceResult(BaseModel):
    """Per-source event extraction metadata."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_url: str
    firm_name: str
    firm_kind: str
    source_provider: str
    status: Literal["success", "failed"]
    event_count: int
    error_type: str | None = None
    message: str | None = None


class EventPullResult(BaseModel):
    """Serializable artifact for one recruiting-event extraction run."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    source_count: int
    successful_source_count: int
    failed_source_count: int
    event_count: int
    sources: list[EventPullSourceResult]
    events: list[RecruitingEventListing]
    failures: list[EventPullFailure]


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
