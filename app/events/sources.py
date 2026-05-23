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
    EventSourceConfig(
        firm_name="Morgan Stanley",
        firm_kind="finance",
        event_page_url="https://www.morganstanley.com/careers/events-aggregate",
        source_provider="morgan_stanley_events",
    ),
    EventSourceConfig(
        firm_name="NVIDIA",
        firm_kind="technology",
        event_page_url="https://www.nvidia.com/en-us/about-nvidia/careers/university-recruiting/events-calendar/",
        source_provider="nvidia_university_events",
    ),
]


CANDIDATE_EVENT_SOURCES: list[EventSourceConfig] = [
    EventSourceConfig(
        firm_name="Amazon",
        firm_kind="technology",
        event_page_url="https://hiring.amazon.com/hiring-process/hiring-events",
        source_provider="amazon_hiring_events",
        firm_aliases=["Amazon", "AWS", "Amazon Student Programs"],
    ),
    EventSourceConfig(
        firm_name="Amazon",
        firm_kind="technology",
        event_page_url="https://studentaffairs.umbc.edu/news-events/events/event/152501/",
        source_scope="university_calendar",
        firm_aliases=["Amazon", "AWS", "Amazon Student Programs"],
    ),
    EventSourceConfig(
        firm_name="Meta",
        firm_kind="technology",
        event_page_url="https://app.joinhandshake.com/employers/meta-8954",
        source_scope="handshake_public",
        firm_aliases=["Meta", "Facebook", "Meta University"],
    ),
    EventSourceConfig(
        firm_name="Meta",
        firm_kind="technology",
        event_page_url="https://careers.umd.edu/events/event-calendar/gear-meta-university-2025",
        source_scope="university_calendar",
        firm_aliases=["Meta", "Facebook", "Meta University"],
    ),
    EventSourceConfig(
        firm_name="Apple",
        firm_kind="technology",
        event_page_url="https://images.apple.com/careers/il/work-at-apple/students.html",
        firm_aliases=["Apple", "Careers at Apple", "Apple Retail"],
    ),
    EventSourceConfig(
        firm_name="Apple",
        firm_kind="technology",
        event_page_url="https://www.northampton.edu/events/2026/04/employer-spotlight-apple.html",
        source_scope="university_calendar",
        firm_aliases=["Apple", "Careers at Apple", "Apple Retail"],
    ),
    EventSourceConfig(
        firm_name="Microsoft",
        firm_kind="technology",
        event_page_url="https://careers.microsoft.com/v2/global/en/events.html",
        firm_aliases=["Microsoft"],
    ),
    EventSourceConfig(
        firm_name="Google",
        firm_kind="technology",
        event_page_url="https://joinhandshake.com/students/events",
        source_scope="handshake_public",
        firm_aliases=["Google", "Careers OnAir"],
    ),
    EventSourceConfig(
        firm_name="Northrop Grumman",
        firm_kind="industrial",
        event_page_url="https://www.northropgrumman.com/careers/northrop-grumman-events",
        source_provider="eightfold_events",
        firm_aliases=["Northrop Grumman"],
    ),
]
