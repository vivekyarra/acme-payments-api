"""Deliver queued webhooks from the ``webhook_deliveries`` outbox table.

Orders write a row to the outbox in the same transaction as the order itself,
so an event is never lost if the process dies mid-request. This worker picks
up pending rows and hands them to the sender.

Run it as a loop with ``python -m app.workers.outbox``, or let the API
schedule ``drain_outbox`` as a FastAPI background task after each write.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time

from app.config import Settings
from app.db import connect, transaction
from app.logging import get_logger
from app.webhooks.sender import WebhookSender

log = get_logger(__name__)

# Only one drain at a time per process; overlapping drains would double-send.
_drain_lock = threading.Lock()


def pending(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, url, payload FROM webhook_deliveries"
        " WHERE status = 'pending' ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()


def process_batch(conn: sqlite3.Connection, sender: WebhookSender, limit: int = 50) -> int:
    """Try every pending delivery once. Returns how many were processed."""
    rows = pending(conn, limit)
    for row in rows:
        result = sender.send(row["url"], json.loads(row["payload"]))
        new_status = "delivered" if result.ok else "failed"
        with transaction(conn):
            conn.execute(
                "UPDATE webhook_deliveries"
                " SET status = ?, attempts = attempts + ?, last_error = ?"
                " WHERE id = ?",
                (new_status, result.attempts, result.error, row["id"]),
            )
        log.info("delivery %s -> %s", row["id"], new_status)
    return len(rows)


def drain_outbox(settings: Settings, sender: WebhookSender | None = None) -> int:
    """Process pending deliveries until none are left. Returns how many ran."""
    if not _drain_lock.acquire(blocking=False):
        return 0  # another drain is already running
    own_sender = sender is None
    sender = sender or WebhookSender(timeout=settings.webhook_timeout_seconds)
    conn = connect(settings.database_path)
    try:
        total = 0
        while n := process_batch(conn, sender):
            total += n
        return total
    finally:
        conn.close()
        if own_sender:
            sender.close()
        _drain_lock.release()


def run_forever(settings: Settings, interval_seconds: float = 2.0) -> None:
    log.info("outbox worker started (every %.1fs)", interval_seconds)
    while True:
        drain_outbox(settings)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    from app import logging as app_logging

    s = Settings.from_env()
    app_logging.configure(s.log_level)
    run_forever(s)
