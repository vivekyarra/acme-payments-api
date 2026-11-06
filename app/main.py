"""Application factory. Run with: uv run uvicorn app.main:app --reload"""

from __future__ import annotations

import time

from fastapi import FastAPI, Request

from app import logging as app_logging
from app.api import errors
from app.api.orders import router as orders_router
from app.config import Settings
from app.db import connect, run_migrations

log = app_logging.get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app_logging.configure(settings.log_level)

    conn = connect(settings.database_path)
    try:
        applied = run_migrations(conn)
    finally:
        conn.close()
    if applied:
        log.info("applied migrations: %s", ", ".join(applied))

    app = FastAPI(title="demo-shop", version="0.1.0")
    app.state.settings = settings
    errors.register(app)
    app.include_router(orders_router)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"ok": True}

    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` looks up `app` lazily, so importing this module
    # (e.g. from tests) does not create shop.sqlite3 as a side effect.
    if name == "app":
        return create_app()
    raise AttributeError(name)
