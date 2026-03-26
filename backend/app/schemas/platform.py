from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IssueNodeTokenRequest(BaseModel):
    label: str | None = None
    expires_hours: int = Field(default=72, ge=1, le=720)


class NodeTokenResponse(BaseModel):
    node_registration_token: str
    expires_at: datetime
    label: str | None


class NodeTokenListResponse(BaseModel):
    id: int
    label: str | None
    expires_at: datetime
    revoked: bool
    used_node_key: str | None
    last_used_at: datetime | None
    created_at: datetime


class NodeRegisterRequest(BaseModel):
    node_id: str
    device_fingerprint: str
    hostname: str
    system: str
    machine: str
    shared_percent_preference: int = Field(default=10, ge=1, le=100)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    seller_intent: str | None = None
    docker_status: str | None = None
    swarm_state: str | None = None
    node_class: str | None = None


class NodeHeartbeatRequest(BaseModel):
    node_id: str
    status: str = "available"
    docker_status: str | None = None
    swarm_state: str | None = None
    capabilities: dict[str, Any] | None = None


class NodeResponse(BaseModel):
    id: int
    seller_user_id: int
    node_key: str
    device_fingerprint: str
    hostname: str
    system: str
    machine: str
    status: str
    shared_percent_preference: int
    node_class: str | None
    capabilities: dict[str, Any]
    seller_intent: str | None
    docker_status: str | None
    swarm_state: str | None
    ready_for_registry_push: bool
    needs_docker_setup: bool
    needs_wireguard_setup: bool
    needs_codex_setup: bool
    needs_node_token: bool
    last_heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ImageReportRequest(BaseModel):
    node_id: str
    repository: str
    tag: str
    digest: str | None = None
    registry: str
    source_image: str | None = None
    status: str = "uploaded"


class ImageArtifactResponse(BaseModel):
    id: int
    seller_user_id: int
    node_id: int | None
    repository: str
    tag: str
    digest: str | None
    registry: str
    source_image: str | None
    status: str
    push_ready: bool
    created_at: datetime
    updated_at: datetime


class ImageOfferCreateRequest(BaseModel):
    image_artifact_id: int


class ImageOfferProbeRequest(BaseModel):
    timeout_seconds: int = Field(default=180, ge=30, le=600)


class ImageOfferResponse(BaseModel):
    id: int
    seller_user_id: int
    node_id: int
    image_artifact_id: int
    repository: str
    tag: str
    digest: str | None
    runtime_image_ref: str
    offer_status: str
    probe_status: str
    probe_measured_capabilities: dict[str, Any]
    pricing_error: str | None
    current_reference_price_cny_per_hour: float | None
    current_billable_price_cny_per_hour: float | None
    current_price_snapshot_id: int | None
    last_probed_at: datetime | None
    last_priced_at: datetime | None
    pricing_stale_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BuyerCatalogOfferResponse(BaseModel):
    offer_id: int
    seller_node_key: str
    repository: str
    tag: str
    runtime_image_ref: str
    offer_status: str
    probe_status: str
    current_billable_price_cny_per_hour: float | None
    pricing_stale_at: datetime | None
    probe_measured_capabilities: dict[str, Any]


class BuyerOrderCreateRequest(BaseModel):
    offer_id: int
    requested_duration_minutes: int = Field(default=60, ge=1, le=720)


class BuyerOrderRedeemRequest(BaseModel):
    license_token: str


class BuyerOrderResponse(BaseModel):
    id: int
    offer_id: int
    seller_node_key: str
    repository: str
    tag: str
    runtime_image_ref: str
    requested_duration_minutes: int
    issued_hourly_price_cny: float
    order_status: str
    license_token: str
    license_redeemed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BuyerOrderRedeemResponse(BaseModel):
    order_id: int
    offer_id: int
    seller_node_key: str
    runtime_image_ref: str
    requested_duration_minutes: int
    issued_hourly_price_cny: float
    order_status: str
    license_token: str


class BuyerWalletResponse(BaseModel):
    buyer_user_id: int
    balance_cny_credits: float
    created_at: datetime
    updated_at: datetime


class WalletLedgerResponse(BaseModel):
    id: int
    buyer_user_id: int
    session_id: int | None
    usage_charge_id: int | None
    entry_type: str
    amount_delta_cny: float
    balance_after: float
    detail: dict[str, Any]
    created_at: datetime


class PlatformOverviewResponse(BaseModel):
    seller_id: int
    node_count: int
    image_count: int
    nodes: list[NodeResponse]
    images: list[ImageArtifactResponse]


class CodexProviderResponse(BaseModel):
    name: str
    base_url: str
    wire_api: str
    requires_openai_auth: bool


class CodexRuntimeAuthResponse(BaseModel):
    OPENAI_API_KEY: str


class CodexRuntimeBootstrapResponse(BaseModel):
    model_provider: str
    model: str
    review_model: str
    model_reasoning_effort: str
    disable_response_storage: bool
    network_access: str
    windows_wsl_setup_acknowledged: bool
    model_context_window: int
    model_auto_compact_token_limit: int
    provider: CodexProviderResponse
    auth: CodexRuntimeAuthResponse
    auth_source: str


class WireGuardBootstrapRequest(BaseModel):
    node_id: str
    client_public_key: str = Field(min_length=16)


class WireGuardBootstrapResponse(BaseModel):
    node_id: str
    interface_name: str
    client_public_key: str
    client_address: str
    server_endpoint_host: str
    server_endpoint_port: int
    server_public_key: str
    allowed_ips: str
    dns: str | None = None
    persistent_keepalive: int
    network_cidr: str
    activation_mode: str
    server_peer_apply_required: bool
    server_peer_apply_status: str | None = None
    server_peer_apply_error: str | None = None


class SwarmWorkerJoinTokenResponse(BaseModel):
    join_token: str
    manager_host: str
    manager_port: int


class SwarmRemoteStateResponse(BaseModel):
    state: str | None
    node_id: str | None
    node_addr: str | None
    control_available: bool
    nodes: int | None = None
    managers: int | None = None
    cluster_id: str | None = None


class SwarmRemoteOverviewResponse(BaseModel):
    manager_host: str
    manager_port: int
    swarm: SwarmRemoteStateResponse
    node_list: str
    service_list: str


class BuyerRuntimeSessionCreateRequest(BaseModel):
    seller_node_key: str | None = None
    offer_id: int | None = None
    session_mode: str = "code_run"
    source_type: str = "inline_code"
    runtime_image: str = "python:3.12-alpine"
    code_filename: str = "main.py"
    code_content: str = Field(default="", max_length=200_000)
    archive_filename: str | None = None
    archive_content_base64: str = ""
    source_ref: str | None = None
    working_dir: str | None = None
    run_command: list[str] | None = None
    entry_command: list[str] | None = None
    requested_duration_minutes: int = Field(default=30, ge=1, le=720)


class BuyerRuntimeSessionCreateResponse(BaseModel):
    session_id: int
    offer_id: int | None = None
    connect_code: str
    expires_at: datetime
    seller_node_key: str
    runtime_image: str
    session_mode: str
    source_type: str


class BuyerRuntimeSessionRedeemRequest(BaseModel):
    connect_code: str


class BuyerRuntimeSessionRedeemResponse(BaseModel):
    session_id: int
    session_token: str
    access_mode: str
    network_mode: str
    relay_endpoint: str
    runtime_image: str
    status: str


class BuyerRuntimeSessionStatusResponse(BaseModel):
    session_id: int
    offer_id: int | None = None
    seller_node_key: str
    runtime_image: str
    source_type: str
    code_filename: str
    session_mode: str
    network_mode: str
    buyer_wireguard_client_address: str | None = None
    seller_wireguard_target: str | None = None
    status: str
    service_name: str
    relay_endpoint: str
    current_hourly_price_cny: float | None = None
    accrued_usage_cny: float = 0.0
    logs: str
    created_at: datetime
    started_at: datetime | None
    expires_at: datetime | None
    ended_at: datetime | None


class BuyerRuntimeSessionStopResponse(BaseModel):
    session_id: int
    status: str


class BuyerRuntimeSessionRenewRequest(BaseModel):
    additional_minutes: int = Field(default=30, ge=1, le=720)


class BuyerRuntimeSessionRenewResponse(BaseModel):
    session_id: int
    status: str
    expires_at: datetime | None


class BuyerRuntimeSessionWireGuardBootstrapRequest(BaseModel):
    client_public_key: str = Field(min_length=16)


class BuyerRuntimeSessionWireGuardBootstrapResponse(BaseModel):
    session_id: int
    interface_name: str
    client_public_key: str
    client_address: str
    server_endpoint_host: str
    server_endpoint_port: int
    server_public_key: str
    allowed_ips: str
    dns: str | None = None
    persistent_keepalive: int
    network_cidr: str
    seller_wireguard_target: str | None = None
    expires_at: datetime | None = None


class BuyerRuntimeSessionReportRequest(BaseModel):
    session_token: str
    status: str
    logs: str = ""
    exit_code: int | None = None
