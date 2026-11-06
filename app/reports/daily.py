"""Daily sales report: order count and revenue for one UTC calendar day.

Timestamps in the database are UTC, so report days are UTC days too, whatever
timezone the machine running the report is in.

Run it for yesterday with ``python -m app.reports.daily``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone

from app.logging import get_logger

log = get_logger(__name__)

_DB_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class DailyReport:
    day: str
    orders: int
    cancelled: int
    revenue_cents: int


def _utcnow() -> datetime:
    """Current time in UTC. Tests replace this to pin the clock."""
    return datetime.now(timezone.utc)


def yesterday_utc() -> date:
    return _utcnow().date() - timedelta(days=1)


def day_bounds(day: date) -> tuple[str, str]:
    """Start (inclusive) and end (exclusive) of the UTC day ``day``, as stored timestamps."""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start.strftime(_DB_FORMAT), end.strftime(_DB_FORMAT)


def build_daily_report(conn: sqlite3.Connection, day: date | None = None) -> DailyReport:
    if day is None:
        day = yesterday_utc()
    start, end = day_bounds(day)
    row = conn.execute(
        "SELECT"
        "  COUNT(*) AS orders,"
        "  COALESCE(SUM(status = 'cancelled'), 0) AS cancelled,"
        "  COALESCE(SUM(CASE WHEN status != 'cancelled' THEN total_cents END), 0) AS revenue"
        " FROM orders WHERE created_at >= ? AND created_at < ?",
        (start, end),
    ).fetchone()
    report = DailyReport(
        day=day.isoformat(),
        orders=row["orders"],
        cancelled=row["cancelled"],
        revenue_cents=row["revenue"],
    )
    log.info("daily report %s: %s", report.day, report)
    return report


def format_report(report: DailyReport) -> str:
    return (
        f"Sales for {report.day}\n"
        f"  orders:    {report.orders}\n"
        f"  cancelled: {report.cancelled}\n"
        f"  revenue:   {report.revenue_cents / 100:.2f}"
    )


if __name__ == "__main__":
    import json
    import sys

    from app.config import Settings
    from app.db import connect

    conn = connect(Settings.from_env().database_path)
    r = build_daily_report(conn)
    print(json.dumps(asdict(r)) if "--json" in sys.argv else format_report(r))
