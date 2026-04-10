from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CatalogOfferRead(BaseModel):
    id: str
    seller_user_id: str
    swarm_node_id: str
    runtime_image_ref: str
    offer_status: str
    current_billable_price: float | None = None
    probe_measured_capabilities: dict[str, Any] | None = None
    validation_status: str | None = None
    shell_agent_status: str | None = None


class BuyerOrderCreateRequest(BaseModel):
    offer_id: str
    requested_duration_minutes: int = Field(ge=1, le=24 * 60)


class BuyerOrderRead(BaseModel):
    id: str
    buyer_user_id: str
    offer_id: str
    order_no: str
    order_status: str
    issued_hourly_price: float | None = None
    requested_duration_minutes: int
    created_at: datetime
    updated_at: datetime


class AccessCodeRead(BaseModel):
    id: str
    order_id: str
    buyer_user_id: str
    access_code: str
    status: str
    issued_at: datetime
    expires_at: datetime
    redeemed_at: datetime | None = None
    revoked_at: datetime | None = None
    detail: dict[str, Any] | None = None


class BuyerOrderCreateResponse(BaseModel):
    order: BuyerOrderRead
    access_code: AccessCodeRead


class AccessCodeRedeemRequest(BaseModel):
    access_code: str


class AccessCodeRedeemResponse(BaseModel):
    access_code: AccessCodeRead
    can_create_runtime_session: bool
    order: BuyerOrderRead
