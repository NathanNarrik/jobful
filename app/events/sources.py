from __future__ import annotations

from app.models import EventSourceConfig


DEFAULT_EVENT_SOURCES: list[EventSourceConfig] = [
    EventSourceConfig(
        firm_name="Google",
        firm_kind="technology",
        event_page_url="https://www.google.com/about/careers/applications/buildyourfuture/events",
    ),
    EventSourceConfig(
        firm_name="JPMorgan Chase",
        firm_kind="finance",
        event_page_url="https://www.jpmorganchase.com/careers/events",
        source_provider="jpmorgan_events",
    ),
    EventSourceConfig(
        firm_name="NASA",
        firm_kind="government",
        event_page_url="https://www.nasa.gov/events/",
        source_provider="nasa_events",
    ),
]
