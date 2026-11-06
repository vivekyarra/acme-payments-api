"""SQL for orders. Functions take a connection and return plain dicts.

Nothing in here commits; callers own the transaction (see ``app.db.transaction``).
"""

from __future__ import annotations

import sqlite3
from typing import Any

Row = dict[str, Any]

_ORDER_COLUMNS = "id, customer_id, status, currency, total_cents, created_at"


def insert_order(
    conn: sqlite3.Connection,
    *,
    customer_id: str,
    currency: str,
    total_cents: int,
    created_at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO orders (customer_id, currency, total_cents, created_at)"
        " VALUES (?, ?, ?, ?)",
        (customer_id, currency, total_cents, created_at),
    )
    return int(cur.lastrowid)


def insert_items(conn: sqlite3.Connection, order_id: int, items: list[Row]) -> None:
    conn.executemany(
        "INSERT INTO order_items (order_id, sku, quantity, unit_price_cents)"
        " VALUES (?, ?, ?, ?)",
        [(order_id, i["sku"], i["quantity"], i["unit_price_cents"]) for i in items],
    )


def get_order(conn: sqlite3.Connection, order_id: int) -> Row | None:
    row = conn.execute(
        f"SELECT {_ORDER_COLUMNS} FROM orders WHERE id = ?", (order_id,)
    ).fetchone()
    return dict(row) if row else None


def get_items(conn: sqlite3.Connection, order_id: int) -> list[Row]:
    rows = conn.execute(
        "SELECT sku, quantity, unit_price_cents FROM order_items"
        " WHERE order_id = ? ORDER BY id",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_order_with_items(conn: sqlite3.Connection, order_id: int) -> Row | None:
    order = get_order(conn, order_id)
    if order is not None:
        order["items"] = get_items(conn, order_id)
    return order


def list_orders_with_items(conn: sqlite3.Connection) -> list[Row]:
    """Every order, newest first, each with its line items."""
    orders = [
        dict(r)
        for r in conn.execute(f"SELECT {_ORDER_COLUMNS} FROM orders ORDER BY id DESC")
    ]
    for order in orders:
        order["items"] = get_items(conn, order["id"])
    return orders


def set_status(conn: sqlite3.Connection, order_id: int, status: str) -> None:
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))


def count_orders(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
