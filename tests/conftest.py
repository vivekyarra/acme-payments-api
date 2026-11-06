from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect, run_migrations
from app.main import create_app

API_KEY = "test-key"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(database_path=str(tmp_path / "shop.sqlite3"), api_keys=frozenset({API_KEY}))


@pytest.fixture
def client(settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app, headers={"X-API-Key": API_KEY}) as c:
        yield c


@pytest.fixture
def db(settings) -> sqlite3.Connection:
    conn = connect(settings.database_path)
    run_migrations(conn)
    yield conn
    conn.close()


def order_payload(customer_id: str = "cus_1", **overrides) -> dict:
    body = {
        "customer_id": customer_id,
        "currency": "USD",
        "items": [
            {"sku": "MUG-01", "quantity": 2, "unit_price": 12.50},
            {"sku": "TEA-07", "quantity": 1, "unit_price": 4.25},
        ],
    }
    body.update(overrides)
    return body
