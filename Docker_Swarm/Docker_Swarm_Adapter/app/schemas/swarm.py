from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NodeSummary(BaseModel):
    id: str
    hostname: str
    role: str
    status: str
    availability: str
    node_addr: str | None = None
    platform_role: str | None = None
    compute_enabled: bool = False
    compute_node_id: str | None = None
    seller_user_id: str | None = None
    accelerator: str | None = None
    running_tasks: int = 0


class ServiceSummary(BaseModel):
    id: str
    name: str
    mode: str
    replicas: str
    image: str
    ports: str | None = None


class SwarmStateSummary(BaseModel):
    state: str
    node_id: str
    node_addr: str
    control_available: bool
    nodes: int
    managers: int


class SwarmOverviewResponse(BaseModel):
    manager_host: str
    swarm: SwarmStateSummary
    node_list_summary: list[NodeSummary]
    service_list_summary: list[ServiceSummary]


class SwarmNodesResponse(BaseModel):
    nodes: list[NodeSummary]


class NodeSearchResponse(BaseModel):
    nodes: list[NodeSummary]
    total: int
    query: str | None = None
    applied_filters: dict[str, Any] = Field(default_factory=dict)


class NodeTaskSummary(BaseModel):
    id: str | None = None
    name: str
    image: str | None = None
    desired_state: str
    current_state: str
    error: str | None = None
    ports: str | None = None


class NodeInspectRequest(BaseModel):
    node_ref: str


class NodeInspectResponse(BaseModel):
    node: NodeSummary
    platform_labels: dict[str, str]
    raw_labels: dict[str, str]
    tasks: list[NodeTaskSummary]
    recent_error_summary: list[str]


class JoinMaterialRequest(BaseModel):
    seller_user_id: str
    requested_accelerator: str = "gpu"
    requested_compute_node_id: str | None = None
    expected_wireguard_ip: str | None = None


class JoinMaterialResponse(BaseModel):
    join_token: str
    manager_addr: str
    manager_port: int
    registry_host: str
    registry_port: int
    swarm_join_command: str
    claim_required: bool
    recommended_compute_node_id: str
    expected_wireguard_ip: str | None = None
    recommended_labels: dict[str, str]
    next_step: str


class ClaimRequest(BaseModel):
    node_ref: str
    compute_node_id: str
    seller_user_id: str
    accelerator: str = "gpu"


class ClaimResponse(BaseModel):
    status: str
    node: NodeSummary
    applied_labels: dict[str, str]


class AvailabilityRequest(BaseModel):
    node_ref: str
    availability: str


class AvailabilityResponse(BaseModel):
    status: str
    node: NodeSummary


class RemoveRequest(BaseModel):
    node_ref: str
    remove_from_swarm: bool = True
    force: bool = False


class RemoveResponse(BaseModel):
    status: str
    removed_from_swarm: bool
    labels_removed: list[str]
    node: NodeSummary | None = None
    detail: str | None = None


class GenericMessageResponse(BaseModel):
    status: str
    detail: str | None = None


class RawPayloadResponse(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
