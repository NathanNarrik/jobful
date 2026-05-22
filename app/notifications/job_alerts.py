from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.env import load_local_env
from app.models import NormalizedJobRecord
from app.normalizers.relevance import is_cs_relevant_job
from app.notifications.email import EmailConfig, send_email

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobAlertSummary:
    considered: int = 0
    matched: int = 0
    sent: int = 0
    skipped_unconfigured: int = 0
    skipped_disabled: int = 0
    failed: int = 0


def should_alert_for_record(record: NormalizedJobRecord) -> bool:
    return is_recently_posted(record.job.date_posted) and is_cs_relevant_alert_record(record)


def send_new_job_alerts(records: list[NormalizedJobRecord]) -> JobAlertSummary:
    matches = [record for record in records if should_alert_for_record(record)]
    if not matches:
        return JobAlertSummary(considered=len(records))

    if not _alerts_enabled():
        logger.info("Skipping %s new job alert(s); email alerts are disabled", len(matches))
        return JobAlertSummary(
            considered=len(records),
            matched=len(matches),
            skipped_disabled=len(matches),
        )

    config = EmailConfig.from_env()
    if not config.is_configured:
        logger.warning(
            "Skipping %s new job alert(s); missing email settings: %s",
            len(matches),
            ", ".join(config.missing_settings),
        )
        return JobAlertSummary(
            considered=len(records),
            matched=len(matches),
            skipped_unconfigured=len(matches),
        )

    sent = 0
    failed = 0
    try:
        subject, text_body, html_body = render_job_alert_batch(matches)
        send_email(subject, text_body, html_body=html_body, config=config)
        sent = len(matches)
    except Exception:
        failed = len(matches)
        logger.exception("Failed to send new job alert batch for %s job(s)", len(matches))

    return JobAlertSummary(
        considered=len(records),
        matched=len(matches),
        sent=sent,
        failed=failed,
    )


def render_job_alert_batch(records: list[NormalizedJobRecord]) -> tuple[str, str, str]:
    if len(records) == 1:
        record = records[0]
        text_body, html_body = render_job_alert(record)
        return f"New CS job: {record.job.company_name} - {record.job.job_title}", text_body, html_body

    shown_records = records[:75]
    omitted_count = max(0, len(records) - len(shown_records))
    company_count = len({record.job.company_name for record in records})
    subject = f"{len(records)} new CS jobs noticed by Jobful"
    if company_count == 1:
        subject = f"{len(records)} new CS jobs: {records[0].job.company_name}"

    text_lines = [
        f"Jobful noticed {len(records)} newly posted CS jobs across {company_count} companies.",
        "",
    ]
    for index, record in enumerate(shown_records, start=1):
        text_lines.extend(
            [
                f"{index}. {record.job.company_name} - {record.job.job_title}",
                f"   Location: {', '.join(record.job.location) if record.job.location else 'Unknown'}",
                f"   Posted: {_format_datetime(record.job.date_posted)}",
                f"   URL: {record.job.job_url}",
                "",
            ]
        )
    if omitted_count:
        text_lines.append(f"...and {omitted_count} more jobs not shown in this email.")

    rows = "".join(_job_row(record) for record in shown_records)
    omitted_html = f"<p>And {omitted_count} more jobs not shown in this email.</p>" if omitted_count else ""
    html_body = (
        "<h2>New Jobful job alerts</h2>"
        f"<p>Jobful noticed {len(records)} newly posted CS jobs across {company_count} companies.</p>"
        "<table style=\"border-collapse:collapse;width:100%\">"
        "<thead><tr>"
        "<th align=\"left\">Company</th>"
        "<th align=\"left\">Title</th>"
        "<th align=\"left\">Location</th>"
        "<th align=\"left\">Posted</th>"
        "<th align=\"left\">Link</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        f"{omitted_html}"
    )
    return subject, "\n".join(text_lines), html_body


def render_job_alert(record: NormalizedJobRecord) -> tuple[str, str]:
    job = record.job
    normalization = record.normalization
    fields = [
        ("Company", job.company_name),
        ("Title", job.job_title),
        ("Location", ", ".join(job.location) if job.location else "Unknown"),
        ("Posted", _format_datetime(job.date_posted)),
        ("Program", normalization.program_type),
        ("Grad years", ", ".join(str(year) for year in normalization.required_grad_years) or "Not specified"),
        ("Skills", ", ".join(normalization.required_skills[:10]) or "Not specified"),
        ("URL", str(job.job_url)),
    ]
    text_body = "\n".join(f"{label}: {value}" for label, value in fields)
    html_rows = "".join(
        "<tr>"
        f"<th align=\"left\" style=\"padding:6px 12px 6px 0\">{html.escape(label)}</th>"
        f"<td style=\"padding:6px 0\">{html.escape(value)}</td>"
        "</tr>"
        for label, value in fields
    )
    html_body = (
        "<h2>New Jobful job alert</h2>"
        "<table>"
        f"{html_rows}"
        "</table>"
        f"<p><a href=\"{html.escape(str(job.job_url), quote=True)}\">Open job posting</a></p>"
    )
    return text_body, html_body


def _job_row(record: NormalizedJobRecord) -> str:
    job = record.job
    return (
        "<tr>"
        f"<td style=\"padding:6px 12px 6px 0\">{html.escape(job.company_name)}</td>"
        f"<td style=\"padding:6px 12px 6px 0\">{html.escape(job.job_title)}</td>"
        f"<td style=\"padding:6px 12px 6px 0\">{html.escape(', '.join(job.location) if job.location else 'Unknown')}</td>"
        f"<td style=\"padding:6px 12px 6px 0\">{html.escape(_format_datetime(job.date_posted))}</td>"
        f"<td style=\"padding:6px 0\"><a href=\"{html.escape(str(job.job_url), quote=True)}\">Open</a></td>"
        "</tr>"
    )


def _alerts_enabled() -> bool:
    load_local_env()
    value = os.getenv("JOBFUL_EMAIL_ALERTS_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def is_recently_posted(value: datetime | None, *, now: datetime | None = None) -> bool:
    if value is None:
        return False
    current = now or datetime.now(UTC)
    posted_at = value if value.tzinfo else value.replace(tzinfo=UTC)
    window = timedelta(hours=_alert_posted_within_hours())
    future_slop = timedelta(hours=_alert_future_slop_hours())
    return current - window <= posted_at <= current + future_slop


def is_cs_relevant_alert_record(record: NormalizedJobRecord) -> bool:
    return is_cs_relevant_job(
        title=record.job.job_title,
        departments=record.job.departments,
        required_skills=record.normalization.required_skills,
        nice_to_have_skills=record.normalization.nice_to_have_skills,
        description=record.cleaned_description or record.job.raw_description or "",
    )


def _alert_posted_within_hours() -> int:
    load_local_env()
    return _env_int("JOBFUL_ALERT_POSTED_WITHIN_HOURS", 48)


def _alert_future_slop_hours() -> int:
    load_local_env()
    return _env_int("JOBFUL_ALERT_FUTURE_SLOP_HOURS", 6)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "Unknown"
    return value.date().isoformat()


InternshipAlertSummary = JobAlertSummary
send_new_internship_alerts = send_new_job_alerts
render_internship_alert = render_job_alert
