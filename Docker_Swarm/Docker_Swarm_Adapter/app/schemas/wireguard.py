from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WireGuardPeerApplyRequest(BaseModel):
    lease_type: str
    runtime_session_id: str
    peer_payload: dict[str, Any] = Field(default_factory=dict)


class WireGuardPeerRemoveRequest(BaseModel):
    runtime_session_id: str
    lease_type: str


class WireGuardPeerResponse(BaseModel):
    runtime_session_id: str
    lease_type: str
    status: str
    public_key: str | None = None
    client_address: str | None = None
    server_interface: str
    server_public_key: str | None = None
    server_access_ip: str | None = None
    endpoint_host: str | None = None
    endpoint_port: int | None = None
    allowed_ips: list[str] = Field(default_factory=list)
    client_allowed_ips: list[str] = Field(default_factory=list)
    persistent_keepalive: int | None = None
    lease_payload: dict[str, Any] = Field(default_factory=dict)
