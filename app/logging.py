"""Logging setup for the whole app.

Every module gets its logger with ``get_logger(__name__)``. ``configure``
is called once from ``create_app``.
"""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"

_configured = False


def configure(level: str = "INFO") -> None:
    """Send app logs to stderr in a single plain-text format."""
    global _configured
    root = logging.getLogger("app")
    root.setLevel(level.upper())
    if _configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    root.propagate = True
    _configured = True


def get_logger(name: str) -> logging.Logger:
    if not name.startswith("app"):
        name = f"app.{name}"
    return logging.getLogger(name)
