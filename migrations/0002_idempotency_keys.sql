-- 0002_idempotency_keys: remember which order each Idempotency-Key created.
-- scope is a SHA-256 of the caller's API key, so keys from different callers
-- never collide and no API key is stored in the clear. The primary key is what
-- stops two concurrent requests with the same key from both creating an order.

CREATE TABLE idempotency_keys (
    scope         TEXT    NOT NULL,
    key           TEXT    NOT NULL,
    request_hash  TEXT    NOT NULL,
    order_id      INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    created_at    TEXT    NOT NULL,
    PRIMARY KEY (scope, key)
);
