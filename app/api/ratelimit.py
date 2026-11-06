"""Request limiting, keyed by API key.

Right now every request is allowed: the limiter only counts requests so the
numbers show up in logs. Real per-key limits are tracked in issue #5.
"""

from __future__ import annotations

from collections import Counter

from fastapi import Depends

from app.api.deps import require_api_key
from app.logging import get_logger

log = get_logger(__name__)


class RequestCounter:
    """Counts requests per API key. Does not limit anything (yet)."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def hit(self, api_key: str) -> int:
        self.counts[api_key] += 1
        return self.counts[api_key]


counter = RequestCounter()


def track_request(api_key: str = Depends(require_api_key)) -> str:
    n = counter.hit(api_key)
    log.debug("api key ...%s: request #%d", api_key[-4:], n)
    return api_key
