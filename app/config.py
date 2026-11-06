"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _split(value: str) -> frozenset[str]:
    return frozenset(v.strip() for v in value.split(",") if v.strip())


@dataclass(frozen=True)
class Settings:
    database_path: str = "shop.sqlite3"
    # Comma-separated list of API keys allowed to call the API.
    api_keys: frozenset[str] = field(default_factory=lambda: frozenset({"dev-key"}))
    # Where order events are POSTed. Empty means "don't send webhooks".
    webhook_url: str = ""
    webhook_timeout_seconds: float = 5.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=os.environ.get("SHOP_DATABASE", "shop.sqlite3"),
            api_keys=_split(os.environ.get("SHOP_API_KEYS", "dev-key")),
            webhook_url=os.environ.get("SHOP_WEBHOOK_URL", ""),
            webhook_timeout_seconds=float(os.environ.get("SHOP_WEBHOOK_TIMEOUT", "5")),
            log_level=os.environ.get("SHOP_LOG_LEVEL", "INFO"),
        )
