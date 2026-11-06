from __future__ import annotations

import threading

from app.db import connect
from app.orders import repo, service
from app.orders.models import OrderIn
from conftest import API_KEY, order_payload


def test_retry_returns_original_order_with_same_status(client, db):
    headers = {"Idempotency-Key": "k-1"}
    first = client.post("/orders", json=order_payload(), headers=headers)
    retry = client.post("/orders", json=order_payload(), headers=headers)
    assert first.status_code == retry.status_code == 201
    assert retry.json() == first.json()
    assert repo.count_orders(db) == 1


def test_same_key_different_body_is_422(client, db):
    headers = {"Idempotency-Key": "k-2"}
    client.post("/orders", json=order_payload("cus_a"), headers=headers)
    resp = client.post("/orders", json=order_payload("cus_b"), headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "idempotency_key_reused"
    assert repo.count_orders(db) == 1


def test_different_keys_create_different_orders(client, db):
    a = client.post("/orders", json=order_payload(), headers={"Idempotency-Key": "a"}).json()
    b = client.post("/orders", json=order_payload(), headers={"Idempotency-Key": "b"}).json()
    assert a["id"] != b["id"]
    assert repo.count_orders(db) == 2


def test_no_header_behaves_as_before(client, db):
    client.post("/orders", json=order_payload())
    client.post("/orders", json=order_payload())
    assert repo.count_orders(db) == 2


def test_keys_are_scoped_per_api_key(db):
    order = OrderIn(**order_payload())
    a = service.create_order(db, order, idempotency_key="k", scope=service.idempotency_scope("one"))
    b = service.create_order(db, order, idempotency_key="k", scope=service.idempotency_scope("two"))
    assert a["id"] != b["id"]


def test_api_key_is_not_stored(client, db):
    client.post("/orders", json=order_payload(), headers={"Idempotency-Key": "k-3"})
    (scope,) = db.execute("SELECT scope FROM idempotency_keys").fetchone()
    assert API_KEY not in scope


def test_concurrent_requests_with_same_key_insert_once(settings, db):
    order = OrderIn(**order_payload())
    scope = service.idempotency_scope(API_KEY)
    barrier = threading.Barrier(4)
    results: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        conn = connect(settings.database_path)
        try:
            barrier.wait()
            created = service.create_order(conn, order, idempotency_key="race", scope=scope)
            results.append(created["id"])
        except BaseException as exc:  # surfaced by the assert below
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(set(results)) == 1
    assert repo.count_orders(db) == 1
