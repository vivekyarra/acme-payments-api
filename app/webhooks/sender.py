"""POST order events to a partner's webhook URL.

The sender is synchronous. Transient failures (network errors, HTTP 429 and
5xx) are retried with jittered exponential backoff; permanent ones (other 4xx) are not.
The caller (``app.workers.outbox``) records the result.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.logging import get_logger

log = get_logger(__name__)

SIGNATURE_HEADER = "X-Shop-Signature"


@dataclass
class DeliveryResult:
    ok: bool
    attempts: int
    status_code: int | None = None
    error: str | None = None


def sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def is_transient(status_code: int) -> bool:
    """A failure worth retrying: the partner may recover."""
    return status_code == 429 or status_code >= 500


class WebhookSender:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timeout: float = 5.0,
        secret: str = "",
        max_attempts: int = 4,
        backoff: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._client = client or httpx.Client(timeout=timeout)
        self._secret = secret
        self._max_attempts = max(1, max_attempts)
        self._backoff = backoff
        self._sleep = sleep
        self._jitter = jitter

    def send(self, url: str, payload: dict) -> DeliveryResult:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self._secret:
            headers[SIGNATURE_HEADER] = sign(body, self._secret)

        result = DeliveryResult(ok=False, attempts=0)
        for attempt in range(1, self._max_attempts + 1):
            result = self._attempt(url, body, headers, attempt)
            if result.ok:
                return result
            transient = result.status_code is None or is_transient(result.status_code)
            if not transient or attempt == self._max_attempts:
                return result
            # Full jitter: spread retries so many failed deliveries don't retry in lockstep.
            self._sleep(self._backoff * 2 ** (attempt - 1) * (0.5 + self._jitter()))
        return result

    def _attempt(self, url: str, body: bytes, headers: dict, attempt: int) -> DeliveryResult:
        try:
            response = self._client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("webhook to %s failed (attempt %d): %s", url, attempt, exc)
            return DeliveryResult(ok=False, attempts=attempt, error=str(exc))

        if response.is_success:
            return DeliveryResult(ok=True, attempts=attempt, status_code=response.status_code)

        log.warning("webhook to %s got HTTP %s (attempt %d)", url, response.status_code, attempt)
        return DeliveryResult(
            ok=False,
            attempts=attempt,
            status_code=response.status_code,
            error=f"HTTP {response.status_code}",
        )

    def close(self) -> None:
        self._client.close()
