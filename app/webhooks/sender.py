"""POST order events to a partner's webhook URL.

The sender is synchronous and makes exactly one HTTP attempt per delivery.
The caller (``app.workers.outbox``) records the result.
"""

from __future__ import annotations

import hashlib
import hmac
import json
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


class WebhookSender:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timeout: float = 5.0,
        secret: str = "",
    ) -> None:
        self._client = client or httpx.Client(timeout=timeout)
        self._secret = secret

    def send(self, url: str, payload: dict) -> DeliveryResult:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self._secret:
            headers[SIGNATURE_HEADER] = sign(body, self._secret)

        try:
            response = self._client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("webhook to %s failed: %s", url, exc)
            return DeliveryResult(ok=False, attempts=1, error=str(exc))

        if response.is_success:
            return DeliveryResult(ok=True, attempts=1, status_code=response.status_code)

        log.warning("webhook to %s got HTTP %s", url, response.status_code)
        return DeliveryResult(
            ok=False,
            attempts=1,
            status_code=response.status_code,
            error=f"HTTP {response.status_code}",
        )

    def close(self) -> None:
        self._client.close()
