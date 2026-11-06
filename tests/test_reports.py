from __future__ import annotations

import time
from datetime import date, datetime, timezone

import pytest

from app.reports import daily


def insert(db, created_at: str, total_cents: int, status: str = "pending") -> None:
    db.execute(
        "INSERT INTO orders (customer_id, status, total_cents, created_at) VALUES (?, ?, ?, ?)",
        ("cus_1", status, total_cents, created_at),
    )
    db.commit()


@pytest.fixture
def pin_clock(monkeypatch):
    def pin(iso: str) -> None:
        now = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        monkeypatch.setattr(daily, "_utcnow", lambda: now)

    return pin


@pytest.fixture
def server_in_ist(monkeypatch):
    """Run the test with the process's local timezone set to IST (UTC+5:30)."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this platform")
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_daily_report_counts_one_day(db):
    insert(db, "2026-03-01T00:00:00Z", 500)  # first second of the day
    insert(db, "2026-03-01T09:00:00Z", 1000)
    insert(db, "2026-03-01T15:30:00Z", 2550)
    insert(db, "2026-03-01T16:00:00Z", 999, status="cancelled")
    insert(db, "2026-03-01T23:59:59Z", 50)  # last second of the day
    insert(db, "2026-02-28T23:59:59Z", 7000)  # previous day
    insert(db, "2026-03-02T00:00:00Z", 7000)  # next day

    report = daily.build_daily_report(db, date(2026, 3, 1))

    assert report.orders == 5
    assert report.cancelled == 1
    assert report.revenue_cents == 4100


def test_empty_day(db):
    report = daily.build_daily_report(db, date(2026, 1, 1))
    assert (report.orders, report.cancelled, report.revenue_cents) == (0, 0, 0)


def test_day_bounds_are_utc_midnights():
    assert daily.day_bounds(date(2026, 3, 1)) == ("2026-03-01T00:00:00Z", "2026-03-02T00:00:00Z")


def test_day_bounds_ignore_server_timezone(server_in_ist):
    assert daily.day_bounds(date(2026, 3, 1)) == ("2026-03-01T00:00:00Z", "2026-03-02T00:00:00Z")


def test_report_in_ist_includes_late_utc_order(db, server_in_ist, pin_clock):
    # 23:30 UTC on 1 March is already 2 March in IST; it still belongs to 1 March.
    insert(db, "2026-03-01T23:30:00Z", 1000)
    pin_clock("2026-03-02T01:00:00Z")
    report = daily.build_daily_report(db)
    assert report.day == "2026-03-01"
    assert report.orders == 1


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-03-02T00:30:00Z", "2026-03-01"),
        # 23:30 UTC on 1 March is 05:00 on 2 March in IST; "yesterday" is still 28 Feb.
        ("2026-03-01T23:30:00Z", "2026-02-28"),
    ],
)
def test_default_day_is_yesterday_in_utc(db, pin_clock, now, expected):
    pin_clock(now)
    assert daily.build_daily_report(db).day == expected


def test_format_report():
    text = daily.format_report(daily.DailyReport("2026-03-01", 3, 1, 3550))
    assert "Sales for 2026-03-01" in text
    assert "35.50" in text
