from __future__ import annotations

from app.db import connect, run_migrations


def test_migrations_apply_once(tmp_path):
    conn = connect(str(tmp_path / "m.sqlite3"))
    assert run_migrations(conn) == ["0001_init", "0002_idempotency_keys"]
    assert run_migrations(conn) == []
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"orders", "order_items", "webhook_deliveries", "idempotency_keys", "schema_migrations"} <= tables


def test_order_items_cascade_on_delete(db):
    db.execute(
        "INSERT INTO orders (customer_id, total_cents, created_at) VALUES ('c', 100, '2026-01-01T00:00:00Z')"
    )
    db.execute("INSERT INTO order_items (order_id, sku, quantity, unit_price_cents) VALUES (1, 'X', 1, 100)")
    db.execute("DELETE FROM orders WHERE id = 1")
    assert db.execute("SELECT COUNT(*) FROM order_items").fetchone()[0] == 0
