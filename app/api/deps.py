"""Shared FastAPI dependencies."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings
from app.db import connect


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(settings: Settings = Depends(get_settings)) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.database_path)
    try:
        yield conn
    finally:
        conn.close()


def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    if not x_api_key or x_api_key not in settings.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key header",
        )
    return x_api_key
