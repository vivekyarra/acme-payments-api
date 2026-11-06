"""/orders routes."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.api.deps import get_db, get_settings
from app.api.ratelimit import track_request
from app.config import Settings
from app.orders import service
from app.orders.models import OrderIn, OrderOut
from app.workers.outbox import drain_outbox

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(track_request)])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OrderOut)
def create_order(
    body: OrderIn,
    background: BackgroundTasks,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    order = service.create_order(conn, body, webhook_url=settings.webhook_url)
    if settings.webhook_url:
        background.add_task(drain_outbox, settings)
    return service.to_public(order)


@router.get("", response_model=list[OrderOut])
def list_orders(conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    return [service.to_public(o) for o in service.list_orders(conn)]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return service.to_public(service.get_order(conn, order_id))


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: int,
    background: BackgroundTasks,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    order = service.cancel_order(conn, order_id, webhook_url=settings.webhook_url)
    if settings.webhook_url:
        background.add_task(drain_outbox, settings)
    return service.to_public(order)
