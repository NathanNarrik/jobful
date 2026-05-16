from __future__ import annotations

import argparse
import json
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from db.engine import create_jobful_engine
from db.models import Job, utc_now


def mark_stale(session: Session, *, older_than_hours: int) -> int:
    cutoff = utc_now() - timedelta(hours=older_than_hours)
    result = session.execute(
        update(Job)
        .where(Job.last_seen_at < cutoff, Job.is_active.is_(True))
        .values(is_active=False)
    )
    session.commit()
    return int(result.rowcount or 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mark jobs inactive when they have not been seen recently.")
    parser.add_argument("--older-than-hours", type=int, default=48)
    parser.add_argument("--database-url", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = create_jobful_engine(args.database_url)
    with Session(engine) as session:
        updated = mark_stale(session, older_than_hours=args.older_than_hours)
    print(json.dumps({"jobs_marked_inactive": updated}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
