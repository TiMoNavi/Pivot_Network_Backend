from __future__ import annotations

from seller_client_app.contracts.phase1 import (
    BackendLocatorHint,
    BootstrapStage,
    ExecutionBoundary,
    JoinCompletePayload,
    JoinMaterialEnvelope,
    LocalJoinExecution,
    NodeProbeSummary,
    PHASE1_BOOTSTRAP_SEQUENCE,
    Phase1BootstrapPlan,
    PhaseStagePlan,
)
from seller_client_app.layers import container_runtime, linux_host, linux_substrate


def build_execution_boundaries() -> tuple[ExecutionBoundary, ...]:
    return (
        ExecutionBoundary(
            component="seller_client",
            responsibilities=(
                "run local detect -> prepare -> install -> repair steps",
                "report Linux Host/Linux substrate/Container Runtime facts",
                "submit join-complete with local execution facts and backend locator hints",
            ),
            forbidden_actions=(
                "call Adapter endpoints directly",
                "declare final manager-side acceptance",
            ),
        ),
        ExecutionBoundary(
            component="backend.adapter_client",
            responsibilities=(
                "fetch join-material",
                "run inspect / claim / inspect acceptance flow",
                "decide whether manager identifies the node by the expected WireGuard IP",
            ),
        ),
        ExecutionBoundary(
            component="Docker_Swarm Adapter",
            responsibilities=(
                "provide join-material",
                "inspect nodes for backend acceptance",
                "claim nodes and manage WireGuard dependencies behind backend",
            ),
        ),
    )


def build_probe_summary(join_input: JoinMaterialEnvelope) -> NodeProbeSummary:
    host_probe = linux_host.build_probe(join_input)
    substrate_probe = linux_substrate.build_probe(join_input)
    runtime_probe = container_runtime.build_probe(join_input)
    rollback_checkpoints = (
        *linux_host.build_rollback_checkpoints(),
        *linux_substrate.build_rollback_checkpoints(),
        *container_runtime.build_rollback_checkpoints(),
    )
    return NodeProbeSummary(
        join_session_id=join_input.join_session_id,
        seller_user_id=join_input.seller_user_id,
        bootstrap_sequence=PHASE1_BOOTSTRAP_SEQUENCE,
        expected_wireguard_ip=join_input.expected_wireguard_ip,
        expected_swarm_advertise_addr=join_input.expected_swarm_advertise_addr,
        linux_host=host_probe,
        linux_substrate=substrate_probe,
        container_runtime=runtime_probe,
        rollback_checkpoints=rollback_checkpoints,
        notes=(
            "NodeProbeSummary aggregates runtime-local facts only.",
            "Manager-side acceptance is backend-owned and is not mixed into the local probe summary.",
        ),
    )


def build_join_complete_payload(
    join_input: JoinMaterialEnvelope,
    node_probe_summary: NodeProbeSummary | None = None,
    *,
    local_execution: LocalJoinExecution | None = None,
    backend_locator: BackendLocatorHint | None = None,
) -> JoinCompletePayload:
    summary = node_probe_summary or build_probe_summary(join_input)
    local_execution = local_execution or LocalJoinExecution()
    backend_locator = backend_locator or BackendLocatorHint(
        compute_node_id=join_input.recommended_compute_node_id,
        required_labels=dict(join_input.required_labels),
    )
    return JoinCompletePayload(
        join_session_id=join_input.join_session_id,
        seller_user_id=join_input.seller_user_id,
        bootstrap_sequence=PHASE1_BOOTSTRAP_SEQUENCE,
        expected_wireguard_ip=join_input.expected_wireguard_ip,
        expected_swarm_advertise_addr=join_input.expected_swarm_advertise_addr,
        local_execution=local_execution,
        node_probe_summary=summary,
        backend_locator=backend_locator,
        rollback_checkpoints=summary.rollback_checkpoints,
        notes=(
            "join-complete carries local execution facts, backend locator hints, and local probe summary only.",
            "expected_wireguard_ip stays platform-owned from join-material/session; runtime observations do not overwrite it.",
            "Backend later decides whether manager identifies the node by the expected WireGuard IP.",
        ),
    )


def build_phase1_plan(join_input: JoinMaterialEnvelope) -> Phase1BootstrapPlan:
    host_operations = linux_host.build_operations()
    substrate_operations = linux_substrate.build_operations()
    runtime_operations = container_runtime.build_operations()
    stage_plans = []
    for stage in PHASE1_BOOTSTRAP_SEQUENCE:
        operations = (
            *host_operations.get(stage, ()),
            *substrate_operations.get(stage, ()),
            *runtime_operations.get(stage, ()),
        )
        stage_plans.append(
            PhaseStagePlan(
                stage=stage,
                intent=_stage_intent(stage),
                operations=operations,
            )
        )
    node_probe_summary = build_probe_summary(join_input)
    return Phase1BootstrapPlan(
        join_input=join_input,
        execution_boundaries=build_execution_boundaries(),
        stage_plans=tuple(stage_plans),
        node_probe_summary=node_probe_summary,
        join_complete_template=build_join_complete_payload(join_input, node_probe_summary),
    )


def _stage_intent(stage: BootstrapStage) -> str:
    if stage is BootstrapStage.DETECT:
        return "Collect local Linux Host/Linux substrate/Container Runtime facts before mutating the node."
    if stage is BootstrapStage.PREPARE:
        return "Stage prerequisites and checkpoint rollback paths before local swarm join."
    if stage is BootstrapStage.INSTALL:
        return "Run the backend-provided join material locally and capture post-join correlation hints."
    return "Repair or roll back partial substrate/runtime state without inventing a new control chain."
