from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuntimeTargetNode(BaseModel):
    node_id: str
    hostname: str
    role: str
    status: str
    availability: str
    compute_node_id: str | None = None


class RuntimeImageValidateRequest(BaseModel):
    image_ref: str
    node_ref: str | None = None
    compute_node_id: str | None = None


class ValidationCheck(BaseModel):
    name: str
    ok: bool
    detail: str
    payload: dict[str, Any] | None = None


class RuntimeImageValidateResponse(BaseModel):
    image_ref: str
    node: RuntimeTargetNode
    validation_status: str
    checks: list[ValidationCheck]
    validation_payload: dict[str, Any] = Field(default_factory=dict)


class NodeProbeRequest(BaseModel):
    node_ref: str | None = None
    compute_node_id: str | None = None


class NodeProbeResponse(BaseModel):
    node: RuntimeTargetNode
    probe_status: str
    probe_measured_capabilities: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ServiceInspectRequest(BaseModel):
    service_name: str


class ServiceTaskSummary(BaseModel):
    id: str | None = None
    name: str
    image: str | None = None
    node: str | None = None
    desired_state: str
    current_state: str
    error: str | None = None


class ServiceInspectResponse(BaseModel):
    service_id: str
    service_name: str
    image: str
    mode: str
    status: str
    ports: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[ServiceTaskSummary] = Field(default_factory=list)
    recent_error_summary: list[str] = Field(default_factory=list)
    logs_summary: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class RuntimeBundleResponse(BaseModel):
    session_id: str
    status: str
    runtime_service_name: str | None = None
    gateway_service_name: str | None = None
    network_name: str | None = None
    runtime_service: dict[str, Any] | None = None
    gateway_service: dict[str, Any] | None = None
    connect_metadata: dict[str, Any] = Field(default_factory=dict)
    wireguard_lease_metadata: dict[str, Any] = Field(default_factory=dict)
    recent_error_summary: list[str] = Field(default_factory=list)


class RuntimeSessionBundleCreateRequest(BaseModel):
    session_id: str
    offer_id: str
    compute_node_id: str | None = None
    node_ref: str | None = None
    runtime_image_ref: str
    requested_duration_minutes: int
    buyer_user_id: str
    network_mode: str
    buyer_network: dict[str, Any] = Field(default_factory=dict)
    resource_profile: dict[str, Any] | None = None


class RuntimeSessionBundleInspectRequest(BaseModel):
    session_id: str


class RuntimeSessionBundleRemoveRequest(BaseModel):
    session_id: str
    force: bool = False
