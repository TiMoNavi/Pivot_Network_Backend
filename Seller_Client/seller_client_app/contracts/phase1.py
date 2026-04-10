from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from seller_client_app.contracts.serialization import SerializableContract


class LayerName(str, Enum):
    LINUX_HOST = "Linux Host"
    LINUX_SUBSTRATE = "Linux substrate"
    CONTAINER_RUNTIME = "Container Runtime"


class BootstrapStage(str, Enum):
    DETECT = "detect"
    PREPARE = "prepare"
    INSTALL = "install"
    REPAIR = "repair"


class ProbeStatus(str, Enum):
    PENDING = "pending"
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class ProbeSource(str, Enum):
    SELLER_CLIENT = "seller_client"


class AdapterInteraction(str, Enum):
    NONE = "none"
    BACKEND_ONLY = "backend-only"


class LocalJoinResult(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REPAIR_REQUIRED = "repair_required"


PHASE1_BOOTSTRAP_SEQUENCE: tuple[BootstrapStage, ...] = (
    BootstrapStage.DETECT,
    BootstrapStage.PREPARE,
    BootstrapStage.INSTALL,
    BootstrapStage.REPAIR,
)

PHASE1_SUCCESS_ANCHOR = "join 后 manager 识别到预期 WireGuard IP"
PHASE1_ADAPTER_CAPABILITIES: tuple[str, ...] = ("join-material", "inspect", "claim", "wireguard")
DEFAULT_BOUNDARY_NOTE = "seller client does not call Adapter directly; backend uses adapter_client."


@dataclass(slots=True)
class ProbePoint(SerializableContract):
    point: str
    layer: LayerName
    stage: BootstrapStage
    status: ProbeStatus
    summary: str
    evidence_keys: tuple[str, ...] = ()
    backend_visible: bool = True


@dataclass(slots=True)
class RollbackAction(SerializableContract):
    description: str
    command_hint: str
    reversible: bool = True


@dataclass(slots=True)
class RollbackCheckpoint(SerializableContract):
    checkpoint_id: str
    stage: BootstrapStage
    layer: LayerName
    trigger: str
    resources_touched: tuple[str, ...]
    rollback_actions: tuple[RollbackAction, ...]
    manual_intervention_required: bool = False


@dataclass(slots=True)
class BootstrapOperation(SerializableContract):
    operation_id: str
    stage: BootstrapStage
    layer: LayerName
    summary: str
    execution_owner: str
    produces_contracts: tuple[str, ...] = ()
    adapter_interaction: AdapterInteraction = AdapterInteraction.NONE
    rollback_checkpoint_id: str | None = None


@dataclass(slots=True)
class ExecutionBoundary(SerializableContract):
    component: str
    responsibilities: tuple[str, ...]
    forbidden_actions: tuple[str, ...] = ()


@dataclass(slots=True)
class LinuxHostProbe(SerializableContract):
    join_session_id: str
    seller_user_id: str
    layer: LayerName = LayerName.LINUX_HOST
    reported_phase: BootstrapStage = BootstrapStage.DETECT
    probe_source: ProbeSource = ProbeSource.SELLER_CLIENT
    os_type: str = "Linux"
    hostname: str | None = None
    machine_id: str | None = None
    kernel_release: str | None = None
    architecture: str | None = None
    cpu_cores: int | None = None
    memory_gb: int | None = None
    disk_free_gb: int | None = None
    observed_local_ips: tuple[str, ...] = ()
    probe_points: tuple[ProbePoint, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class LinuxSubstrateProbe(SerializableContract):
    join_session_id: str
    seller_user_id: str
    layer: LayerName = LayerName.LINUX_SUBSTRATE
    reported_phase: BootstrapStage = BootstrapStage.PREPARE
    probe_source: ProbeSource = ProbeSource.SELLER_CLIENT
    wireguard_available: bool | None = None
    wireguard_interface: str = "wg0"
    expected_wireguard_ip: str | None = None
    observed_wireguard_ip: str | None = None
    observed_local_ips: tuple[str, ...] = ()
    docker_available: bool | None = None
    docker_version: str | None = None
    swarm_join_ready: bool | None = None
    probe_points: tuple[ProbePoint, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class ContainerRuntimeProbe(SerializableContract):
    join_session_id: str
    seller_user_id: str
    layer: LayerName = LayerName.CONTAINER_RUNTIME
    reported_phase: BootstrapStage = BootstrapStage.INSTALL
    probe_source: ProbeSource = ProbeSource.SELLER_CLIENT
    runtime_name: str = "docker"
    runtime_socket_access: bool | None = None
    swarm_membership_state: str | None = None
    observed_swarm_advertise_addr: str | None = None
    swarm_node_id_hint: str | None = None
    probe_points: tuple[ProbePoint, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class NodeProbeSummary(SerializableContract):
    join_session_id: str
    seller_user_id: str
    bootstrap_sequence: tuple[BootstrapStage, ...] = PHASE1_BOOTSTRAP_SEQUENCE
    expected_wireguard_ip: str | None = None
    expected_swarm_advertise_addr: str | None = None
    linux_host: LinuxHostProbe = field(default_factory=lambda: LinuxHostProbe(join_session_id="", seller_user_id=""))
    linux_substrate: LinuxSubstrateProbe = field(default_factory=lambda: LinuxSubstrateProbe(join_session_id="", seller_user_id=""))
    container_runtime: ContainerRuntimeProbe = field(default_factory=lambda: ContainerRuntimeProbe(join_session_id="", seller_user_id=""))
    rollback_checkpoints: tuple[RollbackCheckpoint, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class JoinMaterialEnvelope(SerializableContract):
    join_session_id: str
    seller_user_id: str
    manager_addr: str
    manager_port: int
    swarm_join_command: str
    requested_offer_tier: str | None = None
    requested_accelerator: str | None = None
    recommended_compute_node_id: str | None = None
    expected_swarm_advertise_addr: str | None = None
    expected_wireguard_ip: str | None = None
    required_labels: dict[str, str] = field(default_factory=dict)
    registry_host: str | None = None
    registry_port: int | None = None
    adapter_capabilities: tuple[str, ...] = PHASE1_ADAPTER_CAPABILITIES
    boundary_note: str = DEFAULT_BOUNDARY_NOTE

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> JoinMaterialEnvelope:
        adapter_capabilities = tuple(payload.get("adapter_capabilities") or PHASE1_ADAPTER_CAPABILITIES)
        required_labels = dict(payload.get("required_labels") or {})
        return cls(
            join_session_id=str(payload["join_session_id"]),
            seller_user_id=str(payload["seller_user_id"]),
            manager_addr=str(payload["manager_addr"]),
            manager_port=int(payload["manager_port"]),
            swarm_join_command=str(payload["swarm_join_command"]),
            requested_offer_tier=payload.get("requested_offer_tier"),
            requested_accelerator=payload.get("requested_accelerator"),
            recommended_compute_node_id=payload.get("recommended_compute_node_id"),
            expected_swarm_advertise_addr=payload.get("expected_swarm_advertise_addr"),
            expected_wireguard_ip=payload.get("expected_wireguard_ip"),
            required_labels=required_labels,
            registry_host=payload.get("registry_host"),
            registry_port=payload.get("registry_port"),
            adapter_capabilities=adapter_capabilities,
            boundary_note=str(payload.get("boundary_note") or DEFAULT_BOUNDARY_NOTE),
        )


@dataclass(slots=True)
class LocalJoinExecution(SerializableContract):
    join_command_executed: bool = False
    result: LocalJoinResult = LocalJoinResult.PENDING
    reported_phase: BootstrapStage = BootstrapStage.DETECT
    observed_wireguard_ip: str | None = None
    observed_swarm_advertise_addr: str | None = None
    swarm_node_id_hint: str | None = None
    detail: str | None = None


@dataclass(slots=True)
class BackendLocatorHint(SerializableContract):
    compute_node_id: str | None = None
    node_ref: str | None = None
    hostname: str | None = None
    machine_id: str | None = None
    observed_wireguard_ip: str | None = None
    observed_swarm_advertise_addr: str | None = None
    swarm_node_id_hint: str | None = None
    required_labels: dict[str, str] = field(default_factory=dict)

@dataclass(slots=True)
class JoinCompletePayload(SerializableContract):
    join_session_id: str
    seller_user_id: str
    bootstrap_sequence: tuple[BootstrapStage, ...] = PHASE1_BOOTSTRAP_SEQUENCE
    expected_wireguard_ip: str | None = None
    expected_swarm_advertise_addr: str | None = None
    local_execution: LocalJoinExecution = field(default_factory=LocalJoinExecution)
    node_probe_summary: NodeProbeSummary = field(default_factory=lambda: NodeProbeSummary(join_session_id="", seller_user_id=""))
    backend_locator: BackendLocatorHint = field(default_factory=BackendLocatorHint)
    rollback_checkpoints: tuple[RollbackCheckpoint, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class PhaseStagePlan(SerializableContract):
    stage: BootstrapStage
    intent: str
    operations: tuple[BootstrapOperation, ...]


@dataclass(slots=True)
class Phase1BootstrapPlan(SerializableContract):
    join_input: JoinMaterialEnvelope
    execution_boundaries: tuple[ExecutionBoundary, ...]
    stage_plans: tuple[PhaseStagePlan, ...]
    node_probe_summary: NodeProbeSummary
    join_complete_template: JoinCompletePayload
