"""Daily sales report: order count and revenue for one calendar day.

Run it for yesterday with ``python -m app.reports.daily``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from app.logging import get_logger

log = get_logger(__name__)

_DB_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class DailyReport:
    day: str
    orders: int
    cancelled: int
    revenue_cents: int


def _server_tz() -> tzinfo:
    """The timezone of the machine running the report."""
    return datetime.now().astimezone().tzinfo


def day_bounds(day: date) -> tuple[str, str]:
    """Start (inclusive) and end (exclusive) of ``day``, as stored timestamps."""
    tz = _server_tz()
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return (
        start.astimezone(timezone.utc).strftime(_DB_FORMAT),
        end.astimezone(timezone.utc).strftime(_DB_FORMAT),
    )


def build_daily_report(conn: sqlite3.Connection, day: date | None = None) -> DailyReport:
    if day is None:
        day = date.today() - timedelta(days=1)
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
