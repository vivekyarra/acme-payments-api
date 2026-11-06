from __future__ import annotations

import json

import httpx

from app.orders import service
from app.orders.models import OrderIn
from app.webhooks.sender import SIGNATURE_HEADER, WebhookSender, sign
from app.workers.outbox import drain_outbox
from conftest import order_payload

HOOK_URL = "https://partner.example/hooks"


def sender_with(handler) -> WebhookSender:
    return WebhookSender(httpx.Client(transport=httpx.MockTransport(handler)), secret="s3cret", sleep=lambda _s: None)


def test_send_success_is_signed():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        seen["sig"] = request.headers[SIGNATURE_HEADER]
        return httpx.Response(204)

    result = sender_with(handler).send(HOOK_URL, {"event": "order.created"})
    assert result.ok and result.attempts == 1 and result.status_code == 204
    assert seen["sig"] == sign(seen["body"], "s3cret")


def test_send_reports_http_failure():
    result = sender_with(lambda r: httpx.Response(500)).send(HOOK_URL, {})
    assert not result.ok
    assert result.error == "HTTP 500"


def test_send_reports_network_failure():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    result = sender_with(handler).send(HOOK_URL, {})
    assert not result.ok
    assert "connection refused" in result.error


def test_outbox_delivers_order_created(settings, db):
    service.create_order(db, OrderIn(**order_payload()), webhook_url=HOOK_URL)
    received = []

    def handler(request):
        received.append(json.loads(request.content))
        return httpx.Response(200)

    assert drain_outbox(settings, sender_with(handler)) == 1
    assert received[0]["event"] == "order.created"
    row = db.execute("SELECT status, attempts FROM webhook_deliveries").fetchone()
    assert (row["status"], row["attempts"]) == ("delivered", 1)


def test_no_webhook_url_means_no_outbox_rows(db):
    service.create_order(db, OrderIn(**order_payload()))
    assert db.execute("SELECT COUNT(*) FROM webhook_deliveries").fetchone()[0] == 0


def test_retry_delays_back_off_with_jitter():
    delays = []
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    sender = WebhookSender(
        httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=delays.append,
        jitter=lambda: 0.5,
    )
    result = sender.send("https://partner.example/hooks", {"event": "order.created"})
    assert not result.ok and result.attempts == 4
    assert delays == [0.5, 1.0, 2.0]


def test_permanent_failure_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    sender = WebhookSender(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _s: None)
    assert sender.send("https://partner.example/hooks", {}).attempts == 1
    assert len(calls) == 1
