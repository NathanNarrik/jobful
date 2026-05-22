from __future__ import annotations

import argparse

from app.notifications.email import EmailConfig, send_test_email


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a Jobful test email using JOBFUL_* SMTP settings.")
    parser.add_argument("--to", action="append", dest="recipients", help="Recipient email address. May be repeated.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    recipients = tuple(args.recipients or ())
    config = EmailConfig.from_env(recipients=recipients or None)
    if not config.is_configured:
        print("Email is not configured.")
        print("Missing settings: " + ", ".join(config.missing_settings))
        print("Set JOBFUL_SMTP_HOST, JOBFUL_EMAIL_FROM or JOBFUL_SMTP_USERNAME, and JOBFUL_EMAIL_RECIPIENTS.")
        return 2

    send_test_email(recipients=recipients or None)
    print(f"Sent test email to {', '.join(config.recipients)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
