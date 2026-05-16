from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_serializer


class JobListing(BaseModel):
    """Normalized active job listing emitted by every ATS extractor."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company_name: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    job_url: HttpUrl
    location: str | list[str]
    raw_description: str
    ats_provider: Literal["greenhouse", "lever"]

    @field_serializer("job_url")
    def serialize_job_url(self, job_url: HttpUrl) -> str:
        return str(job_url)
