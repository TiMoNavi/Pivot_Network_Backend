from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class UserRecord:
    id: str
    email: str
    display_name: str
    password_salt: str
    password_hash: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass
class AuthSessionRecord:
    id: str
    user_id: str
    token: str
    scope: str
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime


@dataclass
class OfferRecord:
    id: str
    title: str
    status: str
    seller_user_id: str
    seller_node_id: str
    offer_profile_id: str
    runtime_image_ref: str
    price_snapshot: dict[str, Any]
    capability_summary: dict[str, Any]
    inventory_state: dict[str, Any]
    published_at: datetime | None
    updated_at: datetime
    compute_node_id: str | None = None
    source_join_session_id: str | None = None
    source_assessment_id: str | None = None


@dataclass
class OrderRecord:
    id: str
    buyer_user_id: str
    offer_id: str
    status: str
    requested_duration_minutes: int
    price_snapshot: dict[str, Any]
    runtime_bundle_status: str | None
    access_grant_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class AccessGrantRecord:
    id: str
    buyer_user_id: str
    order_id: str
    runtime_session_id: str | None
    status: str
    grant_type: str
    connect_material_payload: dict[str, Any]
    issued_at: datetime
    expires_at: datetime
    activated_at: datetime | None
    revoked_at: datetime | None


@dataclass
class SellerCapabilityAssessmentRecord:
    id: str
    seller_user_id: str
    onboarding_session_id: str | None
    compute_node_id: str | None
    node_ref: str | None
    assessment_status: str
    requested_offer_tier: str | None
    requested_accelerator: str | None
    request_snapshot: dict[str, Any]
    sources_used: dict[str, Any]
    measured_capabilities: dict[str, Any]
    pricing_decision: dict[str, Any]
    runtime_image_validation: dict[str, Any]
    recommended_offer: dict[str, Any]
    warnings: list[str]
    apply_offer: bool
    apply_result: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class JoinSessionRecord:
    id: str
    seller_user_id: str
    status: str
    one_time_token: str
    requested_offer_tier: str | None
    requested_accelerator: str
    requested_compute_node_id: str | None
    swarm_join_material: dict[str, Any]
    required_labels: dict[str, str]
    expected_wireguard_ip: str | None
    expires_at: datetime
    last_heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class LinuxHostProbeRecord:
    join_session_id: str
    seller_user_id: str
    reported_phase: str | None
    host_name: str | None
    os_name: str | None
    distribution_name: str | None
    kernel_release: str | None
    virtualization_available: bool | None
    sudo_available: bool | None
    observed_ips: list[str]
    notes: list[str]
    raw_payload: dict[str, Any]
    recorded_at: datetime


@dataclass
class LinuxSubstrateProbeRecord:
    join_session_id: str
    seller_user_id: str
    reported_phase: str | None
    distribution_name: str | None
    kernel_release: str | None
    docker_available: bool | None
    docker_version: str | None
    wireguard_available: bool | None
    gpu_available: bool | None
    cpu_cores: int | None
    memory_gb: int | None
    disk_free_gb: int | None
    observed_ips: list[str]
    observed_wireguard_ip: str | None
    observed_advertise_addr: str | None
    observed_data_path_addr: str | None
    notes: list[str]
    raw_payload: dict[str, Any]
    recorded_at: datetime


@dataclass
class ContainerRuntimeProbeRecord:
    join_session_id: str
    seller_user_id: str
    reported_phase: str | None
    runtime_name: str | None
    runtime_version: str | None
    engine_available: bool | None
    image_store_accessible: bool | None
    network_ready: bool | None
    observed_images: list[str]
    notes: list[str]
    raw_payload: dict[str, Any]
    recorded_at: datetime


@dataclass
class JoinCompleteRecord:
    join_session_id: str
    seller_user_id: str
    reported_phase: str | None
    node_ref: str | None
    compute_node_id: str | None
    observed_wireguard_ip: str | None
    observed_advertise_addr: str | None
    observed_data_path_addr: str | None
    notes: list[str]
    raw_payload: dict[str, Any]
    submitted_at: datetime


@dataclass
class CorrectionRecord:
    id: str
    join_session_id: str
    seller_user_id: str
    reported_phase: str | None
    source_surface: str | None
    correction_action: str
    target_wireguard_ip: str | None
    observed_advertise_addr: str | None
    observed_data_path_addr: str | None
    notes: list[str]
    raw_payload: dict[str, Any]
    recorded_at: datetime


@dataclass
class ManagerAddressOverrideRecord:
    id: str
    join_session_id: str
    seller_user_id: str
    reported_phase: str | None
    source_surface: str | None
    override_target_addr: str
    override_reason: str
    notes: list[str]
    raw_payload: dict[str, Any]
    recorded_at: datetime


@dataclass
class AuthoritativeEffectiveTargetRecord:
    id: str
    join_session_id: str
    seller_user_id: str
    reported_phase: str | None
    source_surface: str | None
    effective_target_addr: str
    effective_target_reason: str
    notes: list[str]
    raw_payload: dict[str, Any]
    recorded_at: datetime


@dataclass
class ManagerAcceptanceRecord:
    status: str
    expected_wireguard_ip: str | None
    observed_manager_node_addr: str | None
    matched: bool | None
    node_ref: str | None
    compute_node_id: str | None
    checked_at: datetime | None
    detail: str | None


@dataclass
class MinimumTcpValidationRecord:
    join_session_id: str
    seller_user_id: str
    reported_phase: str | None
    target_addr: str | None
    target_port: int
    protocol: str
    reachable: bool
    validated_against_manager_target: bool
    validated_against_effective_target: bool
    effective_target_addr: str | None
    effective_target_source: str | None
    truth_authority: str
    detail: str | None
    notes: list[str]
    raw_payload: dict[str, Any]
    checked_at: datetime


@dataclass
class InMemoryStore:
    users: dict[str, UserRecord] = field(default_factory=dict)
    users_by_email: dict[str, str] = field(default_factory=dict)
    auth_sessions_by_token: dict[str, AuthSessionRecord] = field(default_factory=dict)
    offers: dict[str, OfferRecord] = field(default_factory=dict)
    capability_assessments: dict[str, SellerCapabilityAssessmentRecord] = field(default_factory=dict)
    orders: dict[str, OrderRecord] = field(default_factory=dict)
    access_grants: dict[str, AccessGrantRecord] = field(default_factory=dict)
    join_sessions: dict[str, JoinSessionRecord] = field(default_factory=dict)
    linux_host_probes_by_session_id: dict[str, LinuxHostProbeRecord] = field(default_factory=dict)
    linux_substrate_probes_by_session_id: dict[str, LinuxSubstrateProbeRecord] = field(default_factory=dict)
    container_runtime_probes_by_session_id: dict[str, ContainerRuntimeProbeRecord] = field(default_factory=dict)
    join_completions_by_session_id: dict[str, JoinCompleteRecord] = field(default_factory=dict)
    corrections_by_session_id: dict[str, list[CorrectionRecord]] = field(default_factory=dict)
    manager_address_override_by_session_id: dict[str, ManagerAddressOverrideRecord] = field(default_factory=dict)
    authoritative_effective_target_by_session_id: dict[str, AuthoritativeEffectiveTargetRecord] = field(default_factory=dict)
    manager_acceptance_by_session_id: dict[str, ManagerAcceptanceRecord] = field(default_factory=dict)
    manager_acceptance_history_by_session_id: dict[str, list[ManagerAcceptanceRecord]] = field(default_factory=dict)
    minimum_tcp_validation_by_session_id: dict[str, MinimumTcpValidationRecord] = field(default_factory=dict)

    def seed_offers(self) -> None:
        if self.offers:
            return

        now = datetime.now(UTC)
        seeded = [
            OfferRecord(
                id="offer-medium-gpu",
                title="Medium GPU Runtime",
                status="listed",
                seller_user_id="seed-seller-1",
                seller_node_id="seed-node-1",
                compute_node_id="seed-node-1",
                offer_profile_id="profile-medium-gpu",
                runtime_image_ref="registry.example.com/pivot/runtime:python-gpu-v1",
                price_snapshot={"currency": "CNY", "hourly_price": 12.5},
                capability_summary={"cpu_limit": 8, "memory_limit_gb": 32, "gpu_mode": "shared"},
                inventory_state={"available": True, "reason": None},
                source_join_session_id=None,
                source_assessment_id=None,
                published_at=now,
                updated_at=now,
            ),
            OfferRecord(
                id="offer-small-cpu",
                title="Small CPU Runtime",
                status="listed",
                seller_user_id="seed-seller-2",
                seller_node_id="seed-node-2",
                compute_node_id="seed-node-2",
                offer_profile_id="profile-small-cpu",
                runtime_image_ref="registry.example.com/pivot/runtime:python-cpu-v1",
                price_snapshot={"currency": "CNY", "hourly_price": 4.0},
                capability_summary={"cpu_limit": 2, "memory_limit_gb": 8, "gpu_mode": None},
                inventory_state={"available": True, "reason": None},
                source_join_session_id=None,
                source_assessment_id=None,
                published_at=now,
                updated_at=now,
            ),
        ]
        self.offers = {item.id: item for item in seeded}
