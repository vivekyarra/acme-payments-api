"""Business rules for orders.

Routes call these functions; these functions call ``repo``. Money is converted
to integer cents at the edge so totals never drift.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from decimal import ROUND_HALF_UP, Decimal

from app.db import transaction, utcnow_iso
from app.logging import get_logger
from app.orders import repo
from app.orders.models import OrderIn

log = get_logger(__name__)

ORDER_CREATED = "order.created"
ORDER_CANCELLED = "order.cancelled"


class OrderNotFound(Exception):
    def __init__(self, order_id: int) -> None:
        super().__init__(order_id)
        self.order_id = order_id


class InvalidTransition(Exception):
    pass


class IdempotencyKeyReused(Exception):
    """The Idempotency-Key was already used for a request with a different body."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def to_cents(amount: float) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> float:
    return cents / 100


def order_total_cents(items: list[dict]) -> int:
    return sum(i["quantity"] * i["unit_price_cents"] for i in items)


def idempotency_scope(api_key: str) -> str:
    """Namespace for Idempotency-Keys: one per caller, without storing the API key."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def request_fingerprint(order: OrderIn) -> str:
    canonical = json.dumps(order.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_order(
    conn: sqlite3.Connection,
    order: OrderIn,
    *,
    webhook_url: str = "",
    idempotency_key: str | None = None,
    scope: str = "",
) -> dict:
    """Insert the order and its items, and queue an ``order.created`` webhook.

    With an ``idempotency_key``, a repeat of the same request returns the order
    the first one created instead of inserting another. The key row is written
    in the same transaction as the order, so the table's primary key decides
    the winner when two requests race; the loser rolls back and replays.
    """
    if idempotency_key is None:
        return _insert_order(conn, order, webhook_url=webhook_url)

    fingerprint = request_fingerprint(order)
    replay = _replay(conn, scope, idempotency_key, fingerprint)
    if replay is not None:
        return replay
    try:
        return _insert_order(
            conn,
            order,
            webhook_url=webhook_url,
            idempotency=(scope, idempotency_key, fingerprint),
        )
    except sqlite3.IntegrityError:
        # Lost a race with a concurrent request using the same key.
        replay = _replay(conn, scope, idempotency_key, fingerprint)
        if replay is None:
            raise  # some other constraint failed
        return replay


def _replay(conn: sqlite3.Connection, scope: str, key: str, fingerprint: str) -> dict | None:
    seen = repo.get_idempotency_key(conn, scope, key)
    if seen is None:
        return None
    if seen["request_hash"] != fingerprint:
        raise IdempotencyKeyReused(key)
    log.info("idempotent replay of order %s", seen["order_id"])
    return get_order(conn, seen["order_id"])


def _insert_order(
    conn: sqlite3.Connection,
    order: OrderIn,
    *,
    webhook_url: str,
    idempotency: tuple[str, str, str] | None = None,
) -> dict:
    items = [
        {"sku": i.sku, "quantity": i.quantity, "unit_price_cents": to_cents(i.unit_price)}
        for i in order.items
    ]
    total = order_total_cents(items)
    with transaction(conn):
        order_id = repo.insert_order(
            conn,
            customer_id=order.customer_id,
            currency=order.currency,
            total_cents=total,
            created_at=utcnow_iso(),
        )
        repo.insert_items(conn, order_id, items)
        if idempotency is not None:
            scope, key, fingerprint = idempotency
            repo.insert_idempotency_key(
                conn,
                scope=scope,
                key=key,
                request_hash=fingerprint,
                order_id=order_id,
                created_at=utcnow_iso(),
            )
        created = repo.get_order_with_items(conn, order_id)
        if webhook_url:
            _enqueue_webhook(conn, created, ORDER_CREATED, webhook_url)
    log.info("order %s created for %s: %s cents", order_id, order.customer_id, total)
    return created


def get_order(conn: sqlite3.Connection, order_id: int) -> dict:
    order = repo.get_order_with_items(conn, order_id)
    if order is None:
        raise OrderNotFound(order_id)
    return order


def list_orders(conn: sqlite3.Connection) -> list[dict]:
    return repo.list_orders_with_items(conn)


def cancel_order(
    conn: sqlite3.Connection, order_id: int, *, webhook_url: str = ""
) -> dict:
    with transaction(conn):
        order = get_order(conn, order_id)
        if order["status"] == "cancelled":
            return order
        if order["status"] != "pending":
            raise InvalidTransition(f"cannot cancel an order that is {order['status']}")
        repo.set_status(conn, order_id, "cancelled")
        order["status"] = "cancelled"
        if webhook_url:
            _enqueue_webhook(conn, order, ORDER_CANCELLED, webhook_url)
    log.info("order %s cancelled", order_id)
    return order


def _enqueue_webhook(conn: sqlite3.Connection, order: dict, event: str, url: str) -> None:
    payload = json.dumps({"event": event, "order": to_public(order)})
    conn.execute(
        "INSERT INTO webhook_deliveries (order_id, event, url, payload, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (order["id"], event, url, payload, utcnow_iso()),
    )


def to_public(order: dict) -> dict:
    """Shape a DB row (cents) into the API response (major units)."""
    return {
        "id": order["id"],
        "customer_id": order["customer_id"],
        "status": order["status"],
        "currency": order["currency"],
        "total": from_cents(order["total_cents"]),
        "created_at": order["created_at"],
        "items": [
            {
                "sku": i["sku"],
                "quantity": i["quantity"],
                "unit_price": from_cents(i["unit_price_cents"]),
            }
            for i in order.get("items", [])
        ],
    }
