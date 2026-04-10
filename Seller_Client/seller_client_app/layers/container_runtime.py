from __future__ import annotations

from seller_client_app.contracts.phase1 import (
    BootstrapOperation,
    BootstrapStage,
    ContainerRuntimeProbe,
    JoinMaterialEnvelope,
    LayerName,
    ProbePoint,
    ProbeStatus,
    RollbackAction,
    RollbackCheckpoint,
)


def build_probe(join_input: JoinMaterialEnvelope) -> ContainerRuntimeProbe:
    return ContainerRuntimeProbe(
        join_session_id=join_input.join_session_id,
        seller_user_id=join_input.seller_user_id,
        reported_phase=BootstrapStage.INSTALL,
        probe_points=(
            ProbePoint(
                point="runtime.docker-socket-access",
                layer=LayerName.CONTAINER_RUNTIME,
                stage=BootstrapStage.DETECT,
                status=ProbeStatus.PENDING,
                summary="Validate that the local runtime can talk to Docker after substrate setup.",
                evidence_keys=("runtime_socket_access",),
            ),
            ProbePoint(
                point="runtime.swarm-membership",
                layer=LayerName.CONTAINER_RUNTIME,
                stage=BootstrapStage.INSTALL,
                status=ProbeStatus.PENDING,
                summary="Capture local runtime view of swarm membership after the join command.",
                evidence_keys=("swarm_membership_state", "swarm_node_id_hint"),
            ),
            ProbePoint(
                point="runtime.advertise-addr",
                layer=LayerName.CONTAINER_RUNTIME,
                stage=BootstrapStage.INSTALL,
                status=ProbeStatus.PENDING,
                summary="Capture the runtime-side advertise address that backend will later check through adapter inspect.",
                evidence_keys=("observed_swarm_advertise_addr",),
            ),
            ProbePoint(
                point="runtime.repair-daemon-state",
                layer=LayerName.CONTAINER_RUNTIME,
                stage=BootstrapStage.REPAIR,
                status=ProbeStatus.PENDING,
                summary="Re-check daemon access, swarm membership, and advertise-address hints during repair.",
                evidence_keys=("runtime_socket_access", "swarm_membership_state", "observed_swarm_advertise_addr"),
            ),
        ),
        notes=(
            "Container Runtime is the lowest local layer in phase 1.",
            "Runtime facts remain local until backend validates them via adapter_client.inspect/claim.",
        ),
    )


def build_operations() -> dict[BootstrapStage, tuple[BootstrapOperation, ...]]:
    return {
        BootstrapStage.DETECT: (
            BootstrapOperation(
                operation_id="runtime.detect-daemon-access",
                stage=BootstrapStage.DETECT,
                layer=LayerName.CONTAINER_RUNTIME,
                summary="Detect Docker daemon socket access before runtime-specific checks.",
                execution_owner="seller_client",
                produces_contracts=("ContainerRuntimeProbe",),
            ),
        ),
        BootstrapStage.PREPARE: (
            BootstrapOperation(
                operation_id="runtime.prepare-correlation-hints",
                stage=BootstrapStage.PREPARE,
                layer=LayerName.CONTAINER_RUNTIME,
                summary="Prepare runtime-side correlation hints that backend can later use for inspect/claim.",
                execution_owner="seller_client",
                produces_contracts=("ContainerRuntimeProbe",),
            ),
        ),
        BootstrapStage.INSTALL: (
            BootstrapOperation(
                operation_id="runtime.capture-post-join-state",
                stage=BootstrapStage.INSTALL,
                layer=LayerName.CONTAINER_RUNTIME,
                summary="Capture runtime-side swarm membership and advertise address after local join execution.",
                execution_owner="seller_client",
                produces_contracts=("ContainerRuntimeProbe", "JoinCompletePayload"),
                rollback_checkpoint_id="runtime.post-join-state",
            ),
        ),
        BootstrapStage.REPAIR: (
            BootstrapOperation(
                operation_id="runtime.reconcile-post-join-state",
                stage=BootstrapStage.REPAIR,
                layer=LayerName.CONTAINER_RUNTIME,
                summary="Re-check runtime daemon, swarm membership, and advertise address during repair.",
                execution_owner="seller_client",
                produces_contracts=("ContainerRuntimeProbe", "NodeProbeSummary"),
            ),
        ),
    }


def build_rollback_checkpoints() -> tuple[RollbackCheckpoint, ...]:
    return (
        RollbackCheckpoint(
            checkpoint_id="runtime.post-join-state",
            stage=BootstrapStage.INSTALL,
            layer=LayerName.CONTAINER_RUNTIME,
            trigger="Runtime reports partial swarm membership or an unexpected advertise address after local join.",
            resources_touched=("docker info swarm state", "runtime advertise address hints"),
            rollback_actions=(
                RollbackAction(
                    description="Refresh runtime-side swarm facts before declaring the join locally complete.",
                    command_hint="docker info && docker node ls",
                    reversible=False,
                ),
            ),
            manual_intervention_required=True,
        ),
    )
