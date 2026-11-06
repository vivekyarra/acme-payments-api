from __future__ import annotations

from datetime import date, timezone

import pytest

from app.reports import daily


def insert(db, created_at: str, total_cents: int, status: str = "pending") -> None:
    db.execute(
        "INSERT INTO orders (customer_id, status, total_cents, created_at) VALUES (?, ?, ?, ?)",
        ("cus_1", status, total_cents, created_at),
    )
    db.commit()


@pytest.fixture
def utc_server(monkeypatch):
    # Pin the "server" timezone so this test does not depend on the machine.
    monkeypatch.setattr(daily, "_server_tz", lambda: timezone.utc)


def test_daily_report_counts_one_day(db, utc_server):
    insert(db, "2026-03-01T09:00:00Z", 1000)
    insert(db, "2026-03-01T15:30:00Z", 2550)
    insert(db, "2026-03-01T16:00:00Z", 999, status="cancelled")
    insert(db, "2026-03-02T09:00:00Z", 7000)  # next day

    report = daily.build_daily_report(db, date(2026, 3, 1))

    assert report.orders == 3
    assert report.cancelled == 1
    assert report.revenue_cents == 3550


def test_empty_day(db, utc_server):
    report = daily.build_daily_report(db, date(2026, 1, 1))
    assert (report.orders, report.cancelled, report.revenue_cents) == (0, 0, 0)


def test_format_report():
    text = daily.format_report(daily.DailyReport("2026-03-01", 3, 1, 3550))
    assert "Sales for 2026-03-01" in text
    assert "35.50" in text
