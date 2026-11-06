"""One test per open behavioural bug. Each is xfail(strict=True):

* while the bug exists, the test fails and CI reports it as "xfailed";
* once someone fixes the bug, the test passes, strict mode turns that into a
  failure, and the fixer removes the xfail marker in the same PR.

So CI proves the bugs are real, and also proves when they are gone.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone

import httpx
import pytest

from app.orders import repo, service
from app.orders.models import OrderIn
from app.reports import daily
from app.webhooks.sender import WebhookSender
from conftest import order_payload


@pytest.mark.xfail(strict=True, reason="issue #2: GET /orders ignores limit and returns every row")
def test_list_orders_is_paginated(client):
    for n in range(30):
        client.post("/orders", json=order_payload(f"cus_{n}"))
    resp = client.get("/orders", params={"limit": 10})
    assert resp.status_code == 200
    assert len(resp.json()) == 10


def test_post_orders_is_idempotent(client, db):
    headers = {"Idempotency-Key": "8d4c1e9a-retry-me"}
    first = client.post("/orders", json=order_payload(), headers=headers)
    retry = client.post("/orders", json=order_payload(), headers=headers)
    assert retry.json()["id"] == first.json()["id"]
    assert repo.count_orders(db) == 1


@pytest.mark.xfail(strict=True, reason="issue #6: webhook sender gives up after one failed attempt")
def test_webhook_sender_retries_transient_failures():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200)

    sender = WebhookSender(httpx.Client(transport=httpx.MockTransport(handler)))
    result = sender.send("https://partner.example/hooks", {"event": "order.created"})
    assert result.ok
    assert result.attempts == 2


@pytest.mark.xfail(strict=True, reason="issue #8: listing orders runs one items query per order")
def test_listing_orders_uses_constant_queries(db):
    for n in range(5):
        service.create_order(db, OrderIn(**order_payload(f"cus_{n}")))

    statements = []
    db.set_trace_callback(statements.append)
    orders = repo.list_orders_with_items(db)
    db.set_trace_callback(None)

    assert len(orders) == 5
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 2


@pytest.mark.xfail(strict=True, reason="issue #10: daily report day boundaries use server local time")
def test_daily_report_uses_utc_days(db, monkeypatch):
    # A server in India (UTC+5:30). An order at 23:30 UTC on 1 March belongs to
    # the 1 March report, whatever timezone the server happens to be in.
    monkeypatch.setattr(daily, "_server_tz", lambda: timezone(timedelta(hours=5, minutes=30)))
    db.execute(
        "INSERT INTO orders (customer_id, total_cents, created_at)"
        " VALUES ('cus_1', 1000, '2026-03-01T23:30:00Z')"
    )
    db.commit()

    report = daily.build_daily_report(db, date(2026, 3, 1))
    assert report.orders == 1
