from __future__ import annotations

from seller_client_app.contracts.phase1 import (
    BootstrapOperation,
    BootstrapStage,
    JoinMaterialEnvelope,
    LayerName,
    LinuxHostProbe,
    ProbePoint,
    ProbeStatus,
    RollbackAction,
    RollbackCheckpoint,
)


def build_probe(join_input: JoinMaterialEnvelope) -> LinuxHostProbe:
    return LinuxHostProbe(
        join_session_id=join_input.join_session_id,
        seller_user_id=join_input.seller_user_id,
        reported_phase=BootstrapStage.DETECT,
        probe_points=(
            ProbePoint(
                point="host.identity",
                layer=LayerName.LINUX_HOST,
                stage=BootstrapStage.DETECT,
                status=ProbeStatus.PENDING,
                summary="Capture hostname, machine-id, kernel release, and architecture before local mutations.",
                evidence_keys=("hostname", "machine_id", "kernel_release", "architecture"),
            ),
            ProbePoint(
                point="host.capacity",
                layer=LayerName.LINUX_HOST,
                stage=BootstrapStage.DETECT,
                status=ProbeStatus.PENDING,
                summary="Capture CPU, memory, and free disk for backend-visible baseline facts.",
                evidence_keys=("cpu_cores", "memory_gb", "disk_free_gb"),
            ),
            ProbePoint(
                point="host.local-ips",
                layer=LayerName.LINUX_HOST,
                stage=BootstrapStage.DETECT,
                status=ProbeStatus.PENDING,
                summary="Capture observed local IPs to help backend correlate the node after local join.",
                evidence_keys=("observed_local_ips",),
            ),
            ProbePoint(
                point="host.privilege-path",
                layer=LayerName.LINUX_HOST,
                stage=BootstrapStage.PREPARE,
                status=ProbeStatus.PENDING,
                summary="Validate whether the bootstrap can reach sudo/root before substrate changes begin.",
                evidence_keys=("effective_user", "sudo_available"),
            ),
            ProbePoint(
                point="host.repair-context",
                layer=LayerName.LINUX_HOST,
                stage=BootstrapStage.REPAIR,
                status=ProbeStatus.PENDING,
                summary="Re-capture host identity and local IP evidence during repair to compare against the original host baseline.",
                evidence_keys=("hostname", "machine_id", "observed_local_ips"),
            ),
        ),
        notes=(
            "Linux Host is the top local layer in phase 1.",
            "This probe reports host facts only and does not express platform acceptance.",
        ),
    )


def build_operations() -> dict[BootstrapStage, tuple[BootstrapOperation, ...]]:
    return {
        BootstrapStage.DETECT: (
            BootstrapOperation(
                operation_id="host.capture-identity",
                stage=BootstrapStage.DETECT,
                layer=LayerName.LINUX_HOST,
                summary="Collect Linux Host identity and baseline resource facts.",
                execution_owner="seller_client",
                produces_contracts=("LinuxHostProbe",),
            ),
        ),
        BootstrapStage.PREPARE: (
            BootstrapOperation(
                operation_id="host.validate-privilege-path",
                stage=BootstrapStage.PREPARE,
                layer=LayerName.LINUX_HOST,
                summary="Validate sudo/root path before substrate and runtime changes.",
                execution_owner="seller_client",
                produces_contracts=("LinuxHostProbe",),
                rollback_checkpoint_id="host.prepare-context",
            ),
        ),
        BootstrapStage.REPAIR: (
            BootstrapOperation(
                operation_id="host.collect-repair-bundle",
                stage=BootstrapStage.REPAIR,
                layer=LayerName.LINUX_HOST,
                summary="Collect host-side evidence before retrying substrate/runtime recovery.",
                execution_owner="seller_client",
                produces_contracts=("NodeProbeSummary",),
            ),
        ),
    }


def build_rollback_checkpoints() -> tuple[RollbackCheckpoint, ...]:
    return (
        RollbackCheckpoint(
            checkpoint_id="host.prepare-context",
            stage=BootstrapStage.PREPARE,
            layer=LayerName.LINUX_HOST,
            trigger="Privilege path is invalid after host preflight has started.",
            resources_touched=("bootstrap workspace", "local execution context"),
            rollback_actions=(
                RollbackAction(
                    description="Remove temporary bootstrap workspace if it was created for the current join session.",
                    command_hint="rm -rf /var/lib/pivot-network/bootstrap/<join_session_id>",
                ),
            ),
        ),
    )
