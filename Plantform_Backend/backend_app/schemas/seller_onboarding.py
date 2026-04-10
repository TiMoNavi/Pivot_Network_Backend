from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


JoinSessionStatus = Literal["issued", "probing", "joined", "verified", "verify_failed", "expired", "closed"]
ManagerAcceptanceStatus = Literal["pending", "matched", "mismatch", "node_not_found", "inspect_failed", "claim_failed"]
ReportedPhase = Literal["detect", "prepare", "install", "repair"]
EffectiveTargetSource = Literal["manager_matched", "operator_override", "backend_correction"]
TruthAuthority = Literal["raw_manager", "backend_correction"]


class SwarmJoinMaterialRead(BaseModel):
    join_token: str
    manager_addr: str
    manager_port: int
    registry_host: str
    registry_port: int
    swarm_join_command: str
    claim_required: bool
    recommended_compute_node_id: str
    expected_wireguard_ip: str | None = None
    recommended_labels: dict[str, str] = Field(default_factory=dict)
    next_step: str


class JoinSessionCreateRequest(BaseModel):
    requested_offer_tier: str | None = Field(default=None, min_length=1, max_length=32)
    requested_accelerator: str = Field(default="gpu", min_length=1, max_length=32)
    requested_compute_node_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_wireguard_ip: str | None = Field(default=None, min_length=1, max_length=64)


class LinuxHostProbeWrite(BaseModel):
    reported_phase: ReportedPhase | None = None
    host_name: str | None = Field(default=None, min_length=1, max_length=128)
    os_name: str | None = Field(default=None, min_length=1, max_length=128)
    distribution_name: str | None = Field(default=None, min_length=1, max_length=128)
    kernel_release: str | None = Field(default=None, min_length=1, max_length=128)
    virtualization_available: bool | None = None
    sudo_available: bool | None = None
    observed_ips: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class LinuxHostProbeRead(LinuxHostProbeWrite):
    join_session_id: str
    seller_user_id: str
    recorded_at: datetime


class LinuxSubstrateProbeWrite(BaseModel):
    reported_phase: ReportedPhase | None = None
    distribution_name: str | None = Field(default=None, min_length=1, max_length=128)
    kernel_release: str | None = Field(default=None, min_length=1, max_length=128)
    docker_available: bool | None = None
    docker_version: str | None = Field(default=None, min_length=1, max_length=128)
    wireguard_available: bool | None = None
    gpu_available: bool | None = None
    cpu_cores: int | None = Field(default=None, ge=0)
    memory_gb: int | None = Field(default=None, ge=0)
    disk_free_gb: int | None = Field(default=None, ge=0)
    observed_ips: list[str] = Field(default_factory=list)
    observed_wireguard_ip: str | None = Field(default=None, min_length=1, max_length=64)
    observed_advertise_addr: str | None = Field(default=None, min_length=1, max_length=128)
    observed_data_path_addr: str | None = Field(default=None, min_length=1, max_length=128)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class LinuxSubstrateProbeRead(LinuxSubstrateProbeWrite):
    join_session_id: str
    seller_user_id: str
    recorded_at: datetime


class ContainerRuntimeProbeWrite(BaseModel):
    reported_phase: ReportedPhase | None = None
    runtime_name: str | None = Field(default=None, min_length=1, max_length=128)
    runtime_version: str | None = Field(default=None, min_length=1, max_length=128)
    engine_available: bool | None = None
    image_store_accessible: bool | None = None
    network_ready: bool | None = None
    observed_images: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ContainerRuntimeProbeRead(ContainerRuntimeProbeWrite):
    join_session_id: str
    seller_user_id: str
    recorded_at: datetime


class NodeResourceSummaryRead(BaseModel):
    docker_available: bool | None = None
    wireguard_available: bool | None = None
    gpu_available: bool | None = None
    cpu_cores: int | None = None
    memory_gb: int | None = None
    disk_free_gb: int | None = None


class NodeProbeSummaryRead(BaseModel):
    join_session_id: str
    seller_user_id: str
    linux_host_probe: LinuxHostProbeRead | None = None
    linux_substrate_probe: LinuxSubstrateProbeRead | None = None
    resource_summary: NodeResourceSummaryRead = Field(default_factory=NodeResourceSummaryRead)
    validation_warnings: list[str] = Field(default_factory=list)
    updated_at: datetime


class JoinCompleteWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reported_phase: ReportedPhase | None = None
    node_ref: str | None = Field(default=None, min_length=1, max_length=128)
    compute_node_id: str | None = Field(default=None, min_length=1, max_length=128)
    observed_wireguard_ip: str | None = Field(default=None, min_length=1, max_length=64)
    observed_advertise_addr: str | None = Field(default=None, min_length=1, max_length=128)
    observed_data_path_addr: str | None = Field(default=None, min_length=1, max_length=128)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_locator(self) -> "JoinCompleteWrite":
        if self.compute_node_id is None and self.node_ref is None:
            raise ValueError("join-complete must include compute_node_id or node_ref.")
        return self


class JoinCompleteRead(JoinCompleteWrite):
    join_session_id: str
    seller_user_id: str
    submitted_at: datetime


class CorrectionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reported_phase: ReportedPhase | None = None
    source_surface: str | None = Field(default=None, min_length=1, max_length=64)
    correction_action: str = Field(min_length=1, max_length=128)
    target_wireguard_ip: str | None = Field(default=None, min_length=1, max_length=64)
    observed_advertise_addr: str | None = Field(default=None, min_length=1, max_length=128)
    observed_data_path_addr: str | None = Field(default=None, min_length=1, max_length=128)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class CorrectionRead(CorrectionWrite):
    correction_id: str
    join_session_id: str
    seller_user_id: str
    recorded_at: datetime


class ManagerAddressOverrideWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reported_phase: ReportedPhase | None = None
    source_surface: str | None = Field(default=None, min_length=1, max_length=64)
    override_target_addr: str = Field(min_length=1, max_length=128)
    override_reason: str = Field(min_length=1, max_length=256)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ManagerAddressOverrideRead(ManagerAddressOverrideWrite):
    override_id: str
    join_session_id: str
    seller_user_id: str
    recorded_at: datetime


class AuthoritativeEffectiveTargetWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reported_phase: ReportedPhase | None = None
    source_surface: str | None = Field(default=None, min_length=1, max_length=64)
    effective_target_addr: str = Field(min_length=1, max_length=128)
    effective_target_reason: str = Field(min_length=1, max_length=256)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ManagerAcceptanceRead(BaseModel):
    status: ManagerAcceptanceStatus
    expected_wireguard_ip: str | None = None
    observed_manager_node_addr: str | None = None
    matched: bool | None = None
    node_ref: str | None = None
    compute_node_id: str | None = None
    checked_at: datetime | None = None
    detail: str | None = None


class ManagerReverifyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reported_phase: ReportedPhase | None = None
    node_ref: str | None = Field(default=None, min_length=1, max_length=128)
    compute_node_id: str | None = Field(default=None, min_length=1, max_length=128)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MinimumTcpValidationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reported_phase: ReportedPhase | None = None
    target_addr: str | None = Field(default=None, min_length=1, max_length=128)
    target_port: int = Field(ge=1, le=65535)
    protocol: Literal["tcp"] = "tcp"
    reachable: bool
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MinimumTcpValidationRead(MinimumTcpValidationWrite):
    join_session_id: str
    seller_user_id: str
    validated_against_manager_target: bool
    validated_against_effective_target: bool = False
    effective_target_addr: str | None = None
    effective_target_source: EffectiveTargetSource | None = None
    truth_authority: TruthAuthority = "raw_manager"
    detail: str | None = None
    checked_at: datetime


class JoinSessionRead(BaseModel):
    session_id: str
    seller_user_id: str
    status: JoinSessionStatus
    one_time_token: str
    requested_offer_tier: str | None = None
    requested_accelerator: str
    requested_compute_node_id: str | None = None
    swarm_join_material: SwarmJoinMaterialRead
    required_labels: dict[str, str] = Field(default_factory=dict)
    expected_wireguard_ip: str | None = None
    probe_summary: NodeProbeSummaryRead | None = None
    container_runtime_probe: ContainerRuntimeProbeRead | None = None
    last_join_complete: JoinCompleteRead | None = None
    correction_history: list[CorrectionRead] = Field(default_factory=list)
    manager_address_override: ManagerAddressOverrideRead | None = None
    manager_acceptance: ManagerAcceptanceRead
    manager_acceptance_history: list[ManagerAcceptanceRead] = Field(default_factory=list)
    effective_target_addr: str | None = None
    effective_target_source: EffectiveTargetSource | None = None
    truth_authority: TruthAuthority = "raw_manager"
    minimum_tcp_validation: MinimumTcpValidationRead | None = None
    expires_at: datetime
    last_heartbeat_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
