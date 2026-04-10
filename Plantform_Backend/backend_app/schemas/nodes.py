from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend_app.schemas.health import AdapterHealthRead


class NodeSummaryRead(BaseModel):
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


class NodeTaskRead(BaseModel):
    id: str | None = None
    name: str
    image: str | None = None
    desired_state: str
    current_state: str
    error: str | None = None
    ports: str | None = None


class NodeDetailRead(BaseModel):
    node: NodeSummaryRead
    platform_labels: dict[str, str] = Field(default_factory=dict)
    raw_labels: dict[str, str] = Field(default_factory=dict)
    tasks: list[NodeTaskRead] = Field(default_factory=list)
    recent_error_summary: list[str] = Field(default_factory=list)


class NodeListRead(BaseModel):
    items: list[NodeSummaryRead] = Field(default_factory=list)
    total: int
    query: str | None = None
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    source: str = "adapter"


class SwarmStateRead(BaseModel):
    state: str
    node_id: str
    node_addr: str
    control_available: bool
    nodes: int
    managers: int


class SwarmServiceRead(BaseModel):
    id: str
    name: str
    mode: str
    replicas: str
    image: str
    ports: str | None = None


class SwarmOverviewRead(BaseModel):
    manager_host: str
    swarm: SwarmStateRead
    node_list_summary: list[NodeSummaryRead] = Field(default_factory=list)
    service_list_summary: list[SwarmServiceRead] = Field(default_factory=list)


class NodePollSnapshotRead(BaseModel):
    polled_at: datetime
    adapter_health: AdapterHealthRead
    overview: SwarmOverviewRead
    nodes: NodeListRead
