"""SQLite connection helpers and a tiny forward-only migration runner.

Migrations are plain ``NNNN_name.sql`` files in ``migrations/``. Each one is
applied once, in filename order, and recorded in ``schema_migrations``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def utcnow_iso() -> str:
    """Current UTC time in the format stored in the database."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Commit on success, roll back on any exception."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}


def run_migrations(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every pending migration. Returns the versions applied this call."""
    done = applied_migrations(conn)
    newly_applied: list[str] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version = path.stem
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        # executescript() commits any open transaction first, then runs the file.
        conn.executescript(f"BEGIN;\n{sql}\nCOMMIT;")
        with transaction(conn):
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, utcnow_iso()),
            )
        newly_applied.append(version)
    return newly_applied


if __name__ == "__main__":  # python -m app.db
    from app.config import Settings

    settings = Settings.from_env()
    with connect(settings.database_path) as c:
        applied = run_migrations(c)
    print("applied:", ", ".join(applied) or "nothing (up to date)")
