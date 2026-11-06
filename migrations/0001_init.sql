-- 0001_init: orders, their line items, and the webhook outbox.
-- Money is stored as integer cents. Timestamps are ISO-8601 UTC strings
-- ("2026-03-01T23:30:00Z") so they sort and compare as text.

CREATE TABLE orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'paid', 'cancelled')),
    currency     TEXT    NOT NULL DEFAULT 'USD',
    total_cents  INTEGER NOT NULL CHECK (total_cents >= 0),
    created_at   TEXT    NOT NULL
);

CREATE INDEX idx_orders_customer ON orders (customer_id);
CREATE INDEX idx_orders_created_at ON orders (created_at);

CREATE TABLE order_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    sku              TEXT    NOT NULL,
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
);

CREATE INDEX idx_order_items_order ON order_items (order_id);

CREATE TABLE webhook_deliveries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL REFERENCES orders (id),
    event       TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'delivered', 'failed')),
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TEXT    NOT NULL
);

CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries (status);
