from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import order_payload


def test_create_order_returns_201_with_total(client):
    resp = client.post("/orders", json=order_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] > 0
    assert body["status"] == "pending"
    assert body["total"] == 29.25
    assert [i["sku"] for i in body["items"]] == ["MUG-01", "TEA-07"]
    assert body["created_at"].endswith("Z")


def test_get_order_round_trips(client):
    created = client.post("/orders", json=order_payload("cus_42")).json()
    resp = client.get(f"/orders/{created['id']}")
    assert resp.status_code == 200
    assert resp.json() == created


def test_list_orders_newest_first_with_items(client):
    first = client.post("/orders", json=order_payload("cus_a")).json()
    second = client.post("/orders", json=order_payload("cus_b")).json()
    resp = client.get("/orders")
    assert resp.status_code == 200
    ids = [o["id"] for o in resp.json()]
    assert ids == [second["id"], first["id"]]
    assert all(len(o["items"]) == 2 for o in resp.json())


def test_cancel_order(client):
    created = client.post("/orders", json=order_payload()).json()
    resp = client.post(f"/orders/{created['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    # Cancelling twice is a no-op, not an error.
    assert client.post(f"/orders/{created['id']}/cancel").status_code == 200


def test_cancel_paid_order_is_conflict(client, db):
    created = client.post("/orders", json=order_payload()).json()
    db.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (created["id"],))
    db.commit()
    resp = client.post(f"/orders/{created['id']}/cancel")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"sku": "MUG-01", "quantity": 0, "unit_price": 1}],
        [{"sku": "MUG-01", "quantity": 1, "unit_price": -1}],
        [{"sku": "", "quantity": 1, "unit_price": 1}],
    ],
)
def test_create_order_rejects_bad_items(client, items):
    resp = client.post("/orders", json=order_payload(items=items))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_requests_without_api_key_are_rejected(client):
    resp = client.get("/orders", headers={"X-API-Key": ""})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_healthz_needs_no_key(client):
    assert client.get("/healthz", headers={"X-API-Key": ""}).json() == {"ok": True}


@pytest.mark.parametrize(
    ("lines", "expected_total"),
    [
        # (quantity, unit_price) pairs. Prices are strings so the expected total is
        # exact; these are the kinds of values that drift when summed as floats.
        ([(1, "0.10"), (1, "0.20")], "0.30"),
        ([(3, "0.10")], "0.30"),
        ([(3, "19.99"), (2, "0.01"), (5, "4.35")], "81.74"),
        ([(5, "1.15"), (4, "2.675"), (1, "0.07")], "16.54"),  # 2.675 rounds half-up to 2.68
        ([(2, "12.50"), (1, "4.25"), (4, "0.33"), (1, "7.77"), (3, "1.01"), (5, "19.99")], "141.32"),
    ],
)
def test_order_totals(client, lines, expected_total):
    """Totals are summed in integer cents, so they are exact for every case.

    The API returns ``total`` as a JSON number; we convert it back to cents
    and compare integers rather than floats with ``==``.
    """
    items = [
        {"sku": f"SKU-{n}", "quantity": qty, "unit_price": float(price)}
        for n, (qty, price) in enumerate(lines)
    ]
    resp = client.post("/orders", json=order_payload(items=items))
    assert resp.status_code == 201
    total_cents = int(Decimal(str(resp.json()["total"])) * 100)
    assert total_cents == int(Decimal(expected_total) * 100)
