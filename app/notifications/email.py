from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.env import load_local_env


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_recipients(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.replace(";", ",").split(",") if item.strip())


@dataclass(frozen=True)
class EmailConfig:
    host: str | None
    port: int
    username: str | None
    password: str | None
    sender: str | None
    recipients: tuple[str, ...]
    use_tls: bool
    timeout_seconds: int

    @classmethod
    def from_env(cls, *, recipients: tuple[str, ...] | None = None) -> "EmailConfig":
        load_local_env()
        username = os.getenv("JOBFUL_SMTP_USERNAME")
        return cls(
            host=os.getenv("JOBFUL_SMTP_HOST"),
            port=int(os.getenv("JOBFUL_SMTP_PORT", "587")),
            username=username,
            password=os.getenv("JOBFUL_SMTP_PASSWORD"),
            sender=os.getenv("JOBFUL_EMAIL_FROM") or username,
            recipients=recipients or _split_recipients(os.getenv("JOBFUL_EMAIL_RECIPIENTS"))
            or ("jobfulandfree@gmail.com",),
            use_tls=_truthy(os.getenv("JOBFUL_SMTP_USE_TLS"), default=True),
            timeout_seconds=int(os.getenv("JOBFUL_SMTP_TIMEOUT_SECONDS", "20")),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.sender and self.recipients)

    @property
    def missing_settings(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.host:
            missing.append("JOBFUL_SMTP_HOST")
        if not self.sender:
            missing.append("JOBFUL_EMAIL_FROM or JOBFUL_SMTP_USERNAME")
        if not self.recipients:
            missing.append("JOBFUL_EMAIL_RECIPIENTS")
        return tuple(missing)


def send_email(
    subject: str,
    text_body: str,
    *,
    html_body: str | None = None,
    config: EmailConfig | None = None,
) -> None:
    config = config or EmailConfig.from_env()
    if not config.is_configured:
        missing = ", ".join(config.missing_settings)
        raise RuntimeError(f"Email is not configured; missing: {missing}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="jobful.local")
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(config.host, config.port, timeout=config.timeout_seconds) as smtp:
        if config.use_tls:
            smtp.starttls()
        if config.username and config.password:
            smtp.login(config.username, config.password)
        smtp.send_message(message)


def send_test_email(*, recipients: tuple[str, ...] | None = None) -> None:
    config = EmailConfig.from_env(recipients=recipients)
    send_email(
        "Jobful test email",
        "This is a test email from Jobful. New job alerts will use this same SMTP path.",
        config=config,
    )
