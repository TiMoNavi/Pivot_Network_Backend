from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BuyerRuntimeSessionCreateRequest(BaseModel):
    access_code: str
    network_mode: str = "wireguard"
    wireguard_public_key: str


class BuyerRuntimeSessionRead(BaseModel):
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
    public_gateway_access_url: str | None = None
    wireguard_gateway_access_url: str | None = None
    shell_embed_url: str | None = None
    workspace_sync_url: str | None = None
    workspace_root: str | None = None
    connect_material_updated_at: datetime | None = None
    started_at: datetime | None = None
    expires_at: datetime
    ended_at: datetime | None = None
    last_synced_at: datetime | None = None


class BuyerConnectMaterialResponse(BaseModel):
    session_id: str
    status: str
    connect_material: dict[str, Any] = Field(default_factory=dict)
    public_gateway_access_url: str | None = None
    wireguard_gateway_access_url: str | None = None
    shell_embed_url: str | None = None
    workspace_sync_url: str | None = None
    workspace_root: str | None = None
    wireguard_profile_fields: dict[str, Any] | None = None
    wireguard_lease: dict[str, Any] | None = None


class WireGuardProfileRead(BaseModel):
    server_public_key: str | None = None
    client_address: str | None = None
    endpoint_host: str | None = None
    endpoint_port: int | None = None
    allowed_ips: list[str] = Field(default_factory=list)
    persistent_keepalive: int | None = None


class BuyerRuntimeClientSessionRead(BaseModel):
    status: str
    expires_at: datetime
    last_heartbeat_at: datetime | None = None
    last_env_report: dict[str, Any] | None = None


class BuyerRuntimeClientBootstrapConfigRead(BaseModel):
    runtime_session_id: str
    client_session: BuyerRuntimeClientSessionRead
    codex_config_toml: str
    codex_auth_json: str
    codex_mcp_launch: dict[str, Any]
    shell_embed_url: str | None = None
    public_gateway_access_url: str | None = None
    wireguard_gateway_access_url: str | None = None
    workspace_sync_url: str | None = None
    workspace_root: str | None = None
    wireguard_profile: WireGuardProfileRead


class BuyerRuntimeClientEnvReportWrite(BaseModel):
    env_report: dict[str, Any]
