from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlatformOverviewResponse(BaseModel):
    adapter_health: dict[str, Any]
    database: str
    counts: dict[str, int] = Field(default_factory=dict)
    last_sync_at: datetime | None = None


class SwarmSyncResponse(BaseModel):
    sync_run_id: str
    sync_scope: str
    status: str
    nodes_changed: int
    services_changed: int
    tasks_changed: int
    error_summary: str | None = None


class PlatformRuntimeSessionRead(BaseModel):
    id: str
    buyer_user_id: str
    seller_node_id: str | None = None
    offer_id: str
    order_id: str
    access_code_id: str
    runtime_image_ref: str
    runtime_service_name: str | None = None
    gateway_service_name: str | None = None
    status: str
    gateway_host: str | None = None
    gateway_port: int | None = None
    network_mode: str
    connect_material_payload: dict[str, Any] | None = None
    connect_material_updated_at: datetime | None = None
    started_at: datetime | None = None
    expires_at: datetime
    ended_at: datetime | None = None
    last_synced_at: datetime | None = None
    gateway_endpoint: dict[str, Any] | None = None
    wireguard_lease: dict[str, Any] | None = None


class PlatformOrderRead(BaseModel):
    id: str
    buyer_user_id: str
    offer_id: str
    order_no: str
    order_status: str
    issued_hourly_price: float | None = None
    requested_duration_minutes: int
    created_at: datetime
    updated_at: datetime


class OperationLogRead(BaseModel):
    id: str
    operation_type: str
    target_type: str
    target_key: str
    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None
    status: str
    error_message: str | None = None
    created_at: datetime


class MaintenanceRunResponse(BaseModel):
    job_name: str
    status: str
    processed_count: int
    success_count: int
    failed_count: int
    details: list[dict[str, Any]] = Field(default_factory=list)
