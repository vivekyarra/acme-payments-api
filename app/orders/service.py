"""Business rules for orders.

Routes call these functions; these functions call ``repo``. Money is converted
to integer cents at the edge so totals never drift.
"""

from __future__ import annotations

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


def to_cents(amount: float) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> float:
    return cents / 100


def order_total_cents(items: list[dict]) -> int:
    return sum(i["quantity"] * i["unit_price_cents"] for i in items)


def create_order(
    conn: sqlite3.Connection, order: OrderIn, *, webhook_url: str = ""
) -> dict:
    """Insert the order and its items, and queue an ``order.created`` webhook."""
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


def list_orders(
    conn: sqlite3.Connection, *, limit: int | None = None, after: int | None = None
) -> list[dict]:
    return repo.list_orders_with_items(conn, limit=limit, after=after)


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
