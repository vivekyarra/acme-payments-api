from __future__ import annotations

import random

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


@pytest.mark.flaky_demo
def test_order_totals(client):
    """Issue #7: this test fails some of the time. Run: uv run pytest -m flaky_demo"""
    items = [
        {
            "sku": f"SKU-{n}",
            "quantity": random.randint(1, 5),
            "unit_price": round(random.uniform(0.01, 20), 2),
        }
        for n in range(random.randint(1, 6))
    ]
    resp = client.post("/orders", json=order_payload(items=items))
    expected = sum(i["quantity"] * i["unit_price"] for i in items)
    assert resp.json()["total"] == expected


def test_list_orders_items_attach_to_the_right_order_in_order(db):
    from app.orders import repo

    for order_id, customer in ((1, "a"), (2, "b"), (3, "c")):
        db.execute(
            "INSERT INTO orders (id, customer_id, total_cents, created_at)"
            " VALUES (?, ?, 0, '2026-01-01T00:00:00Z')",
            (order_id, customer),
        )
    # Interleave inserts so item ids alone would mix the orders up.
    for order_id, sku in ((1, "A1"), (3, "C1"), (1, "A2"), (3, "C2"), (1, "A3")):
        db.execute(
            "INSERT INTO order_items (order_id, sku, quantity, unit_price_cents)"
            " VALUES (?, ?, 1, 100)",
            (order_id, sku),
        )
    db.commit()

    orders = {o["id"]: [i["sku"] for i in o["items"]] for o in repo.list_orders_with_items(db)}
    assert orders == {1: ["A1", "A2", "A3"], 2: [], 3: ["C1", "C2"]}


def test_list_orders_with_no_orders(db):
    from app.orders import repo

    assert repo.list_orders_with_items(db) == []


def test_list_orders_handles_more_ids_than_sqlite_bind_limit(db):
    from app.orders import repo

    n = 40_000  # above SQLITE_MAX_VARIABLE_NUMBER (32766 on modern builds)
    db.executemany(
        "INSERT INTO orders (id, customer_id, total_cents, created_at)"
        " VALUES (?, 'c', 0, '2026-01-01T00:00:00Z')",
        [(i,) for i in range(1, n + 1)],
    )
    db.execute(
        "INSERT INTO order_items (order_id, sku, quantity, unit_price_cents) VALUES (1, 'X', 1, 1)"
    )
    db.commit()
    orders = repo.list_orders_with_items(db)
    assert len(orders) == n
    assert orders[-1]["items"][0]["sku"] == "X"
