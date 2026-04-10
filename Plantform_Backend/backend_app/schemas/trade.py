from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OfferRead(BaseModel):
    id: str
    title: str
    status: str
    seller_user_id: str
    seller_node_id: str
    compute_node_id: str | None = None
    offer_profile_id: str
    runtime_image_ref: str
    price_snapshot: dict[str, Any] = Field(default_factory=dict)
    capability_summary: dict[str, Any] = Field(default_factory=dict)
    inventory_state: dict[str, Any] = Field(default_factory=dict)
    published_at: datetime | None = None
    updated_at: datetime


class OfferListRead(BaseModel):
    items: list[OfferRead] = Field(default_factory=list)
    total: int


class OrderCreateRequest(BaseModel):
    offer_id: str
    requested_duration_minutes: int = Field(ge=1, le=24 * 60)


class OrderRead(BaseModel):
    id: str
    buyer_user_id: str
    offer_id: str
    status: str
    requested_duration_minutes: int
    price_snapshot: dict[str, Any] = Field(default_factory=dict)
    runtime_bundle_status: str | None = None
    access_grant_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AccessGrantRead(BaseModel):
    id: str
    buyer_user_id: str
    order_id: str
    runtime_session_id: str | None = None
    status: str
    grant_type: str
    connect_material_payload: dict[str, Any] = Field(default_factory=dict)
    issued_at: datetime
    expires_at: datetime
    activated_at: datetime | None = None
    revoked_at: datetime | None = None


class OrderActivationRead(BaseModel):
    order: OrderRead
    access_grant: AccessGrantRead


class AccessGrantListRead(BaseModel):
    items: list[AccessGrantRead] = Field(default_factory=list)
    total: int
