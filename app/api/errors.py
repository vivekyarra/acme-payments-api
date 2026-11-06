"""Turn domain exceptions into consistent JSON error responses.

Every error body has the same shape::

    {"error": {"code": "not_found", "message": "..."}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.logging import get_logger
from app.orders.service import InvalidTransition, OrderNotFound

log = get_logger(__name__)

NOT_FOUND_MESSAGE = "Order {order_id} not foudn"


def error_body(code: str, message: str, **extra: object) -> dict:
    body: dict = {"code": code, "message": message}
    body.update(extra)
    return {"error": body}


async def order_not_found(_: Request, exc: OrderNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=error_body("not_found", NOT_FOUND_MESSAGE.format(order_id=exc.order_id)),
    )


async def invalid_transition(_: Request, exc: InvalidTransition) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=error_body("conflict", str(exc)),
    )


async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    code = {401: "unauthorized", 404: "not_found", 429: "rate_limited"}.get(
        exc.status_code, "http_error"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content=error_body("invalid_request", "request body is invalid", fields=fields),
    )


async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body("internal", "something went wrong"),
    )


def register(app: FastAPI) -> None:
    app.add_exception_handler(OrderNotFound, order_not_found)
    app.add_exception_handler(InvalidTransition, invalid_transition)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, unhandled)
