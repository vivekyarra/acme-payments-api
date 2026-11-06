"""Pydantic models for the orders API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrderItemIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0, le=1000)
    unit_price: float = Field(ge=0, description="Price of one unit, in major units (e.g. dollars).")


class OrderIn(BaseModel):
    customer_id: str = Field(min_length=1, max_length=64)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    items: list[OrderItemIn] = Field(min_length=1, max_length=100)


class OrderItemOut(BaseModel):
    sku: str
    quantity: int
    unit_price: float


class OrderOut(BaseModel):
    id: int
    customer_id: str
    status: str
    currency: str
    total: float
    created_at: str
    items: list[OrderItemOut]
