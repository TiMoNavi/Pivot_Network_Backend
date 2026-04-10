from __future__ import annotations

from seller_client_app.contracts.phase1 import (
    BootstrapOperation,
    BootstrapStage,
    JoinMaterialEnvelope,
    LayerName,
    LinuxSubstrateProbe,
    ProbePoint,
    ProbeStatus,
    RollbackAction,
    RollbackCheckpoint,
)


def build_probe(join_input: JoinMaterialEnvelope) -> LinuxSubstrateProbe:
    return LinuxSubstrateProbe(
        join_session_id=join_input.join_session_id,
        seller_user_id=join_input.seller_user_id,
        reported_phase=BootstrapStage.PREPARE,
        expected_wireguard_ip=join_input.expected_wireguard_ip,
        probe_points=(
            ProbePoint(
                point="substrate.wireguard-installation",
                layer=LayerName.LINUX_SUBSTRATE,
                stage=BootstrapStage.DETECT,
                status=ProbeStatus.PENDING,
                summary="Detect WireGuard package, interface, and config file reachability.",
                evidence_keys=("wireguard_available", "wireguard_interface"),
            ),
            ProbePoint(
                point="substrate.wireguard-address",
                layer=LayerName.LINUX_SUBSTRATE,
                stage=BootstrapStage.PREPARE,
                status=ProbeStatus.PENDING,
                summary="Capture the expected and observed WireGuard IP before and after local setup.",
                evidence_keys=("expected_wireguard_ip", "observed_wireguard_ip", "observed_local_ips"),
            ),
            ProbePoint(
                point="substrate.docker-engine",
                layer=LayerName.LINUX_SUBSTRATE,
                stage=BootstrapStage.DETECT,
                status=ProbeStatus.PENDING,
                summary="Detect Docker Engine availability and version on the local node.",
                evidence_keys=("docker_available", "docker_version"),
            ),
            ProbePoint(
                point="substrate.swarm-join-readiness",
                layer=LayerName.LINUX_SUBSTRATE,
                stage=BootstrapStage.PREPARE,
                status=ProbeStatus.PENDING,
                summary="Validate that WireGuard and Docker are ready before local swarm join.",
                evidence_keys=("swarm_join_ready",),
            ),
            ProbePoint(
                point="substrate.repair-network-state",
                layer=LayerName.LINUX_SUBSTRATE,
                stage=BootstrapStage.REPAIR,
                status=ProbeStatus.PENDING,
                summary="Re-check WireGuard, Docker, and local join prerequisites during repair before another attempt.",
                evidence_keys=("wireguard_available", "observed_wireguard_ip", "docker_available", "swarm_join_ready"),
            ),
        ),
        notes=(
            "Linux substrate is the only layer where WireGuard, Docker Engine, and swarm join preparation happen.",
            "The substrate probe captures local execution facts only.",
        ),
    )


def build_operations() -> dict[BootstrapStage, tuple[BootstrapOperation, ...]]:
    return {
        BootstrapStage.DETECT: (
            BootstrapOperation(
                operation_id="substrate.detect-wireguard",
                stage=BootstrapStage.DETECT,
                layer=LayerName.LINUX_SUBSTRATE,
                summary="Detect WireGuard presence and current interface state.",
                execution_owner="seller_client",
                produces_contracts=("LinuxSubstrateProbe",),
            ),
            BootstrapOperation(
                operation_id="substrate.detect-docker-engine",
                stage=BootstrapStage.DETECT,
                layer=LayerName.LINUX_SUBSTRATE,
                summary="Detect Docker Engine binaries, daemon status, and version.",
                execution_owner="seller_client",
                produces_contracts=("LinuxSubstrateProbe",),
            ),
        ),
        BootstrapStage.PREPARE: (
            BootstrapOperation(
                operation_id="substrate.prepare-wireguard",
                stage=BootstrapStage.PREPARE,
                layer=LayerName.LINUX_SUBSTRATE,
                summary="Stage WireGuard config and route prerequisites for the expected private address.",
                execution_owner="seller_client",
                produces_contracts=("LinuxSubstrateProbe",),
                rollback_checkpoint_id="substrate.prepare-network",
            ),
            BootstrapOperation(
                operation_id="substrate.prepare-docker",
                stage=BootstrapStage.PREPARE,
                layer=LayerName.LINUX_SUBSTRATE,
                summary="Ensure Docker Engine can accept the later swarm join command.",
                execution_owner="seller_client",
                produces_contracts=("LinuxSubstrateProbe",),
            ),
        ),
        BootstrapStage.INSTALL: (
            BootstrapOperation(
                operation_id="substrate.join-swarm",
                stage=BootstrapStage.INSTALL,
                layer=LayerName.LINUX_SUBSTRATE,
                summary="Execute the backend-provided swarm join command on the local Linux substrate.",
                execution_owner="seller_client",
                produces_contracts=("JoinCompletePayload",),
                rollback_checkpoint_id="substrate.join-worker",
            ),
        ),
        BootstrapStage.REPAIR: (
            BootstrapOperation(
                operation_id="substrate.repair-network-and-join",
                stage=BootstrapStage.REPAIR,
                layer=LayerName.LINUX_SUBSTRATE,
                summary="Reconcile WireGuard and swarm membership after a failed or partial join attempt.",
                execution_owner="seller_client",
                produces_contracts=("RollbackCheckpoint", "NodeProbeSummary"),
                rollback_checkpoint_id="substrate.repair-network",
            ),
        ),
    }


def build_rollback_checkpoints() -> tuple[RollbackCheckpoint, ...]:
    return (
        RollbackCheckpoint(
            checkpoint_id="substrate.prepare-network",
            stage=BootstrapStage.PREPARE,
            layer=LayerName.LINUX_SUBSTRATE,
            trigger="WireGuard or Docker substrate prerequisites are partially staged and the sequence cannot continue.",
            resources_touched=("/etc/wireguard/wg0.conf", "systemd wireguard state", "docker daemon state"),
            rollback_actions=(
                RollbackAction(
                    description="Restore the previous WireGuard config before any local join retry.",
                    command_hint="install -m 600 <backup_wg_conf> /etc/wireguard/wg0.conf",
                ),
                RollbackAction(
                    description="Restart WireGuard and Docker after restoring their known-good config.",
                    command_hint="systemctl restart wg-quick@wg0 docker",
                ),
            ),
        ),
        RollbackCheckpoint(
            checkpoint_id="substrate.join-worker",
            stage=BootstrapStage.INSTALL,
            layer=LayerName.LINUX_SUBSTRATE,
            trigger="Local swarm join command was attempted but the node did not reach the expected substrate state.",
            resources_touched=("docker swarm membership", "join token usage", "local WireGuard route state"),
            rollback_actions=(
                RollbackAction(
                    description="Leave the partially joined swarm before another attempt.",
                    command_hint="docker swarm leave --force",
                ),
                RollbackAction(
                    description="Refresh WireGuard and Docker state before a retry.",
                    command_hint="systemctl restart wg-quick@wg0 docker",
                ),
            ),
            manual_intervention_required=True,
        ),
        RollbackCheckpoint(
            checkpoint_id="substrate.repair-network",
            stage=BootstrapStage.REPAIR,
            layer=LayerName.LINUX_SUBSTRATE,
            trigger="Repair mode needs to recover a mismatch between local WireGuard state and swarm join state.",
            resources_touched=("wg0 interface", "docker swarm membership"),
            rollback_actions=(
                RollbackAction(
                    description="Re-run the substrate detection probes to confirm whether recovery cleared the mismatch.",
                    command_hint="phase1 detect --join-session <join_session_id>",
                ),
            ),
        ),
    )
