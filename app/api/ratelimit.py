"""Per-API-key rate limiting with token buckets.

Each API key has a bucket holding up to ``burst`` tokens, refilled at ``rate``
tokens per second. A request takes one token; with none left it gets a 429
with a ``Retry-After`` header. One limiter lives on ``app.state.limiter``
(created by ``create_app``), so separate apps never share buckets.
"""

from __future__ import annotations

import math
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import require_api_key
from app.logging import get_logger

log = get_logger(__name__)


def mask_key(api_key: str) -> str:
    """How an API key appears in logs and metrics: its last 4 characters."""
    return f"...{api_key[-4:]}"


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    """Token bucket per API key. Thread-safe: one lock guards every bucket."""

    def __init__(
        self,
        rate: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate <= 0 or burst < 1:
            raise ValueError("rate must be > 0 and burst >= 1")
        self.rate = rate
        self.burst = burst
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self.allowed: Counter[str] = Counter()
        self.rejected: Counter[str] = Counter()

    def acquire(self, api_key: str) -> float:
        """Take one token for ``api_key``.

        Returns 0.0 if the request is allowed, otherwise the number of seconds
        until a token will be available.
        """
        with self._lock:
            now = self._clock()
            bucket = self._buckets.get(api_key)
            if bucket is None:
                bucket = self._buckets[api_key] = _Bucket(tokens=self.burst, updated_at=now)
            else:
                elapsed = max(0.0, now - bucket.updated_at)
                bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate)
                bucket.updated_at = now
            if bucket.tokens >= 1:
                bucket.tokens -= 1
                self.allowed[api_key] += 1
                return 0.0
            self.rejected[api_key] += 1
            return (1 - bucket.tokens) / self.rate

    def metrics(self) -> dict[str, dict[str, int]]:
        """Allowed and rejected request counts per (masked) API key."""
        with self._lock:
            keys = set(self.allowed) | set(self.rejected)
            return {
                mask_key(k): {"allowed": self.allowed[k], "rejected": self.rejected[k]}
                for k in sorted(keys)
            }


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.limiter


def track_request(
    api_key: str = Depends(require_api_key),
    limiter: RateLimiter = Depends(get_limiter),
) -> str:
    wait = limiter.acquire(api_key)
    if wait > 0:
        retry_after = max(1, math.ceil(wait))
        log.warning(
            "rate limited api key %s (%d rejected so far), retry after %ds",
            mask_key(api_key),
            limiter.rejected[api_key],
            retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded for this API key",
            headers={"Retry-After": str(retry_after)},
        )
    return api_key
