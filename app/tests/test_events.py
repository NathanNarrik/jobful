from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_events_db
from app.api.main import app
from app.db.models import Base
from app.events.db.import_events import import_events, match_source_for_event
from app.events.db.models import EventBase, EventSource, RecruitingEvent
from app.events.extract import CompanyEventPageExtractor
from app.events.extract import classify_source_exception
from app.events.extract import parse_date_and_time
from app.models import EventSourceConfig, RecruitingEventListing


class FakeResponse:
    def __init__(self, *, text: str = "", payload: object | None = None, status_code: int = 200, content_type: str = "text/html") -> None:
        self.text = text
        self._payload = payload
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            error = requests.HTTPError(f"{self.status_code} Client Error")
            error.response = self
            raise error


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, *args: object, **kwargs: object) -> FakeResponse:
        return self.response


def sample_source() -> EventSourceConfig:
    return EventSourceConfig(
        firm_name="Example Capital",
        firm_kind="finance",
        event_page_url="https://example.com/events",
    )


def sample_event(**overrides: object) -> RecruitingEventListing:
    starts_at = datetime.now(UTC) + timedelta(days=10)
    values = {
        "firm_name": "Example Capital",
        "firm_kind": "finance",
        "event_title": "Engineering Recruiting Info Session",
        "event_url": "https://example.com/events/info",
        "registration_url": "https://example.com/events/info/register",
        "source_provider": "company_events",
        "source_event_id": "event-123",
        "event_type": "info_session",
        "audience_tags": ["students", "engineers"],
        "location": ["Virtual"],
        "location_type": "virtual",
        "starts_at": starts_at,
        "ends_at": starts_at + timedelta(hours=1),
        "timezone": "UTC",
        "description": "A virtual recruiting session for software engineering students.",
        "raw_payload": {"id": "event-123"},
        "content_hash": "e" * 64,
        "extracted_at": datetime.now(UTC),
    }
    values.update(overrides)
    return RecruitingEventListing.model_validate(values)


class RecruitingEventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        EventBase.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False, future=True)

        def override_db():
            with self.Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_events_db] = override_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_event_tables_import_and_upsert(self) -> None:
        with Session(self.engine) as session:
            first = import_events(session, [sample_event()], sample_source())
            second = import_events(session, [sample_event(event_title="Updated Info Session")], sample_source())

            self.assertEqual(first.sources_inserted, 1)
            self.assertEqual(first.events_inserted, 1)
            self.assertEqual(second.events_updated, 1)
            self.assertEqual(session.scalar(select(RecruitingEvent.event_title)), "Updated Info Session")

    def test_past_events_are_inactive(self) -> None:
        past = sample_event(
            content_hash="f" * 64,
            source_event_id="past-event",
            starts_at=datetime.now(UTC) - timedelta(days=3),
            ends_at=datetime.now(UTC) - timedelta(days=2),
        )

        with Session(self.engine) as session:
            import_events(session, [past], sample_source())
            event = session.scalar(select(RecruitingEvent).where(RecruitingEvent.content_hash == "f" * 64))

        self.assertFalse(event.is_active)

    def test_events_api_filters_and_detail(self) -> None:
        with Session(self.engine) as session:
            import_events(session, [sample_event()], sample_source())
            event_id = str(session.scalar(select(RecruitingEvent.id)))

        events = self.client.get("/events?firm=Example&event_type=info_session&location_type=virtual&search=engineering").json()
        detail = self.client.get(f"/events/{event_id}").json()
        sources = self.client.get("/event-sources").json()

        self.assertEqual(events["total"], 1)
        self.assertEqual(events["items"][0]["firm_name"], "Example Capital")
        self.assertEqual(detail["event_title"], "Engineering Recruiting Info Session")
        self.assertEqual(sources[0]["active_event_count"], 1)

    def test_json_ld_events_extract(self) -> None:
        html = """
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Event",
          "name": "Campus Engineering Night",
          "startDate": "2026-06-15T18:00:00Z",
          "endDate": "2026-06-15T19:00:00Z",
          "url": "https://example.com/events/campus",
          "location": {"name": "Online"},
          "description": "Virtual info session for students and engineers."
        }
        </script>
        """
        extractor = CompanyEventPageExtractor(sample_source())
        events = extractor._extract_json_ld(BeautifulSoup(html, "html.parser"))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_title, "Campus Engineering Night")
        self.assertEqual(events[0].location_type, "virtual")
        self.assertIn("students", events[0].audience_tags)

    def test_ics_events_extract(self) -> None:
        content = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:ics-123
SUMMARY:Career Fair
DTSTART:20260620T170000Z
DTEND:20260620T200000Z
LOCATION:Main Campus
DESCRIPTION:In-person student recruiting event.
URL:https://example.com/events/fair
END:VEVENT
END:VCALENDAR
"""
        extractor = CompanyEventPageExtractor(sample_source())
        events = extractor._extract_ics(content, "https://example.com/events.ics")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "career_fair")
        self.assertEqual(events[0].location_type, "in_person")

    def test_jpmorgan_event_json_maps_to_event(self) -> None:
        extractor = CompanyEventPageExtractor(sample_source())
        events = []
        item = {
            "event_name": "Online Academy - Engineering",
            "date_start": "02/06/2026",
            "date_end": "02/06/2026",
            "start_time": "5:30 PM",
            "end_time": "7:00 PM",
            "event_classification": "Informational/Networking",
            "city": "Tokyo",
            "external_description": "<p>Student workshop for engineers.</p>",
        }
        starts_at = parse_date_and_time(item["date_start"], item["start_time"])

        self.assertEqual(starts_at, datetime(2026, 2, 6, 17, 30, tzinfo=UTC))
        event = extractor._event_from_mapping(
            {
                "name": item["event_name"],
                "startDate": starts_at.isoformat(),
                "description": item["external_description"],
            },
            fallback_url="https://example.com/events",
        )
        events.append(event)

        self.assertEqual(events[0].event_title, "Online Academy - Engineering")

    def test_google_escaped_event_cards_extract_as_evergreen_events(self) -> None:
        html = r"""
        \u003cdiv data-cy=\"resultsList\" data-tracking-title=\"Careers OnAir\" data-glue-filter-event-type=\"google-hosted virtual\"\u003e
          \u003ca href=\"https://careersonair.withgoogle.com/\"\u003e
            \u003cspan\u003eREGISTRATION IS NOW OPEN\u003c/span\u003e
            \u003ch3\u003eCareers OnAir\u003c/h3\u003e
            \u003cspan\u003eVIRTUAL\u003c/span\u003e
            \u003cp\u003eGoogle recruiting sessions for students and engineers.\u003c/p\u003e
          \u003c/a\u003e
        \u003c/div\u003e
        """
        extractor = CompanyEventPageExtractor(
            EventSourceConfig(
                firm_name="Google",
                firm_kind="technology",
                event_page_url="https://www.google.com/about/careers/applications/buildyourfuture/events",
            )
        )
        events = extractor._extract_google_event_cards(extractor._decoded_soup(html))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_title, "Careers OnAir")
        self.assertEqual(events[0].location_type, "virtual")
        self.assertIsNotNone(events[0].ends_at)
        self.assertGreater(events[0].ends_at, events[0].starts_at)
        self.assertIn("students", events[0].audience_tags)

    def test_morgan_stanley_event_json_extracts_future_events(self) -> None:
        source = EventSourceConfig(
            firm_name="Morgan Stanley",
            firm_kind="finance",
            event_page_url="https://www.morganstanley.com/careers/events-aggregate",
            source_provider="morgan_stanley_events",
        )
        payload = {
            "status": 200,
            "eventResults": [
                {
                    "eventId": "ms-1",
                    "eventTitle": "2026 Technology Early Careers Webinar",
                    "eventStartDate": "Wednesday, September 09, 2026",
                    "eventEndDate": "Wednesday, September 09, 2026",
                    "eventTime": "03:00 PM GMT",
                    "eventDetailUrl": "/careers/events/technology-webinar",
                    "eventType": "Webinar",
                    "eventCountry": "Virtual",
                    "eventHtmlDescription": "<p>Student recruiting webinar for engineers.</p>",
                }
            ],
        }
        extractor = CompanyEventPageExtractor(source, session=FakeSession(FakeResponse(payload=payload)))
        events = extractor._extract_morgan_stanley_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].firm_name, "Morgan Stanley")
        self.assertEqual(events[0].event_type, "webinar")
        self.assertEqual(events[0].starts_at, datetime(2026, 9, 9, 15, 0, tzinfo=UTC))

    def test_nvidia_university_json_extracts_events(self) -> None:
        source = EventSourceConfig(
            firm_name="NVIDIA",
            firm_kind="technology",
            event_page_url="https://www.nvidia.com/en-us/about-nvidia/careers/university-recruiting/events-calendar/",
            source_provider="nvidia_university_events",
        )
        payload = [
            {
                "title": "Grace Hopper Career Fair",
                "startDate": "2026-09-18",
                "endDate": "2026-09-19",
                "location": "Virtual",
                "url": "https://example.com/nvidia-ghc",
                "venue": "Online",
            }
        ]
        extractor = CompanyEventPageExtractor(source, session=FakeSession(FakeResponse(payload=payload)))
        events = extractor._extract_nvidia_university_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_title, "Grace Hopper Career Fair")
        self.assertEqual(events[0].event_type, "career_fair")
        self.assertIn("students", events[0].audience_tags)

    def test_eightfold_embedded_event_data_extracts_registration_event(self) -> None:
        source = EventSourceConfig(
            firm_name="Northrop Grumman",
            firm_kind="industrial",
            event_page_url="https://jobs.northropgrumman.com/events/candidate/registration?plannedEventId=abc",
            source_provider="eightfold_events",
        )
        html = """
        <script>
        window.__DATA__ = {"eventData": {
          "name": "Military and Veteran Virtual Information Session",
          "plannedEventEncId": "abc",
          "eventLandingURL": "https://jobs.northropgrumman.com/events/candidate/registration?plannedEventId=abc",
          "eventLocationType": "virtual_event",
          "selectedTimezone": "America/New_York",
          "startTimestamp": 1779307200,
          "endTimestamp": 1779312600,
          "description": "<p>Recruiting session for military candidates.</p>"
        }};
        </script>
        """
        extractor = CompanyEventPageExtractor(source, session=FakeSession(FakeResponse(text=html)))
        events = extractor._extract_eightfold_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].location_type, "virtual")
        self.assertEqual(events[0].source_event_id, "abc")
        self.assertEqual(str(events[0].registration_url), "https://jobs.northropgrumman.com/events/candidate/registration?plannedEventId=abc")

    def test_public_university_event_page_maps_major_tech_aliases(self) -> None:
        source = EventSourceConfig(
            firm_name="Public Campus Events",
            firm_kind="other",
            event_page_url="https://example.edu/events",
            source_scope="university_calendar",
        )
        html = """
        <article class="event">
          <h2>Amazon Student Programs Career Corner</h2>
          <time datetime="2026-08-23T17:00:00Z"></time>
          <p>Join AWS recruiters for an internship info session on campus.</p>
          <a href="/events/amazon">Register</a>
        </article>
        <article class="event">
          <h2>Gear Up for Meta University</h2>
          <time datetime="2026-09-10T19:00:00Z"></time>
          <p>Meta recruiting event for first-year and second-year students.</p>
        </article>
        <article class="event">
          <h2>Employer Spotlight - Apple</h2>
          <time datetime="2026-10-01T16:00:00Z"></time>
          <p>Meet Apple Retail recruiters and learn about student careers.</p>
        </article>
        """
        extractor = CompanyEventPageExtractor(source)
        events = extractor._extract_public_recruiting_cards(BeautifulSoup(html, "html.parser"))

        self.assertEqual([event.firm_name for event in events], ["Amazon", "Meta", "Apple"])
        self.assertTrue(all(event.firm_kind == "technology" for event in events))

    def test_handshake_auth_required_is_source_status_not_failure(self) -> None:
        source = EventSourceConfig(
            firm_name="Meta",
            firm_kind="technology",
            event_page_url="https://app.joinhandshake.com/events/123",
            source_scope="handshake_public",
        )
        error = FakeResponse(status_code=403)
        try:
            error.raise_for_status()
        except Exception as exc:
            status = classify_source_exception(source, exc)

        self.assertEqual(status, "auth-required")

    def test_empty_import_marks_source_status_empty(self) -> None:
        with Session(self.engine) as session:
            import_events(session, [], sample_source())
            source_status = session.scalar(select(EventSource.source_status))

        self.assertEqual(source_status, "empty")

    def test_import_matches_events_to_same_host_source_before_same_firm_source(self) -> None:
        hiring_source = EventSourceConfig(
            firm_name="Amazon",
            firm_kind="technology",
            event_page_url="https://hiring.amazon.com/hiring-process/hiring-events",
            source_provider="amazon_hiring_events",
        )
        campus_source = EventSourceConfig(
            firm_name="Amazon",
            firm_kind="technology",
            event_page_url="https://studentaffairs.umbc.edu/news-events/events/event/152501/",
            source_scope="university_calendar",
        )
        event = sample_event(
            firm_name="Amazon",
            firm_kind="technology",
            event_url="https://studentaffairs.umbc.edu/news-events/events/event/152501/",
            registration_url="https://studentaffairs.umbc.edu/news-events/events/event/152501/",
            content_hash="a" * 64,
            source_event_id="amazon-campus",
        )

        with Session(self.engine) as session:
            import_events(session, [], hiring_source)
            import_events(session, [], campus_source)
            sources = session.execute(select(EventSource)).scalars().all()
            matched = match_source_for_event({source.source_url: source for source in sources}, event)

        self.assertEqual(matched.source_url, str(campus_source.event_page_url))


if __name__ == "__main__":
    unittest.main()
