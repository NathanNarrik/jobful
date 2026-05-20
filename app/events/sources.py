from __future__ import annotations

from app.models import EventSourceConfig


DEFAULT_EVENT_SOURCES: list[EventSourceConfig] = [
    EventSourceConfig(
        firm_name="Google",
        firm_kind="technology",
        event_page_url="https://buildyourfuture.withgoogle.com/events",
    ),
    EventSourceConfig(
        firm_name="Microsoft",
        firm_kind="technology",
        event_page_url="https://careers.microsoft.com/v2/global/en/events.html",
    ),
    EventSourceConfig(
        firm_name="Amazon",
        firm_kind="technology",
        event_page_url="https://www.amazon.jobs/content/en/career-programs/university/events",
    ),
    EventSourceConfig(
        firm_name="JPMorgan Chase",
        firm_kind="finance",
        event_page_url="https://careers.jpmorgan.com/us/en/students/events",
    ),
    EventSourceConfig(
        firm_name="Deloitte",
        firm_kind="consulting",
        event_page_url="https://www.deloitte.com/us/en/careers/events.html",
    ),
    EventSourceConfig(
        firm_name="NASA",
        firm_kind="government",
        event_page_url="https://www.nasa.gov/careers/pathways/",
    ),
]
