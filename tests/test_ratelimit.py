from __future__ import annotations

import logging
import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api.ratelimit import RateLimiter
from app.main import create_app
from conftest import API_KEY


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_burst_then_reject(clock):
    limiter = RateLimiter(rate=10, burst=20, clock=clock)
    assert all(limiter.acquire("k") == 0 for _ in range(20))
    wait = limiter.acquire("k")
    assert wait == pytest.approx(0.1)
    assert limiter.rejected["k"] == 1


def test_refill_over_time(clock):
    limiter = RateLimiter(rate=10, burst=20, clock=clock)
    for _ in range(20):
        limiter.acquire("k")
    assert limiter.acquire("k") > 0

    clock.now += 0.5  # 5 tokens back
    assert all(limiter.acquire("k") == 0 for _ in range(5))
    assert limiter.acquire("k") > 0

    clock.now += 60  # refill is capped at the burst size
    assert all(limiter.acquire("k") == 0 for _ in range(20))
    assert limiter.acquire("k") > 0


def test_keys_do_not_affect_each_other(clock):
    limiter = RateLimiter(rate=1, burst=2, clock=clock)
    limiter.acquire("a")
    limiter.acquire("a")
    assert limiter.acquire("a") > 0
    assert limiter.acquire("b") == 0
    assert limiter.rejected == {"a": 1}


def test_concurrent_acquires_never_over_admit(clock):
    limiter = RateLimiter(rate=1, burst=100, clock=clock)  # clock frozen: no refill
    barrier = threading.Barrier(8)
    allowed = []

    def worker() -> None:
        barrier.wait()
        allowed.append(sum(limiter.acquire("k") == 0 for _ in range(50)))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(allowed) == 100
    assert limiter.allowed["k"] == 100
    assert limiter.rejected["k"] == 300


def test_metrics_mask_keys(clock):
    limiter = RateLimiter(rate=1, burst=1, clock=clock)
    limiter.acquire("secret-abcd")
    limiter.acquire("secret-abcd")
    assert limiter.metrics() == {"...abcd": {"allowed": 1, "rejected": 1}}


def test_over_limit_is_429_with_retry_after(settings, caplog):
    app = create_app(replace(settings, rate_limit_per_second=0.5, rate_limit_burst=2))
    with TestClient(app, headers={"X-API-Key": API_KEY}) as client:
        assert client.get("/orders").status_code == 200
        assert client.get("/orders").status_code == 200
        with caplog.at_level(logging.WARNING, logger="app"):
            resp = client.get("/orders")

        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "rate_limited"
        assert resp.headers["Retry-After"] == "2"
        assert any(f"...{API_KEY[-4:]}" in r.getMessage() for r in caplog.records)
        assert API_KEY not in caplog.text

        metrics = client.get("/ops/ratelimit").json()
        assert metrics == {f"...{API_KEY[-4:]}": {"allowed": 2, "rejected": 1}}


def test_each_app_has_its_own_limiter(settings):
    tight = replace(settings, rate_limit_per_second=0.1, rate_limit_burst=1)
    for _ in range(2):
        with TestClient(create_app(tight), headers={"X-API-Key": API_KEY}) as client:
            assert client.get("/orders").status_code == 200
