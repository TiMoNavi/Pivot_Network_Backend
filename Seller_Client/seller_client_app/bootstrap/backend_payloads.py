from __future__ import annotations

from typing import Any

from seller_client_app.contracts.phase1 import (
    BootstrapStage,
    JoinCompletePayload,
    LocalJoinExecution,
    NodeProbeSummary,
)


def build_backend_write_payloads(
    node_probe_summary: NodeProbeSummary,
    *,
    join_complete_payload: JoinCompletePayload | None = None,
) -> dict[str, dict[str, Any]]:
    join_complete_payload = join_complete_payload or JoinCompletePayload(
        join_session_id=node_probe_summary.join_session_id,
        seller_user_id=node_probe_summary.seller_user_id,
        bootstrap_sequence=node_probe_summary.bootstrap_sequence,
        expected_wireguard_ip=node_probe_summary.expected_wireguard_ip,
        expected_swarm_advertise_addr=node_probe_summary.expected_swarm_advertise_addr,
        local_execution=LocalJoinExecution(reported_phase=node_probe_summary.container_runtime.reported_phase),
        node_probe_summary=node_probe_summary,
        rollback_checkpoints=node_probe_summary.rollback_checkpoints,
    )
    return {
        "linux_host_probe": build_linux_host_probe_write(node_probe_summary),
        "linux_substrate_probe": build_linux_substrate_probe_write(
            node_probe_summary,
            join_complete_payload=join_complete_payload,
        ),
        "container_runtime_probe": build_container_runtime_probe_write(node_probe_summary),
        "join_complete": build_join_complete_write(join_complete_payload),
    }


def build_linux_host_probe_write(
    node_probe_summary: NodeProbeSummary,
    *,
    reported_phase: BootstrapStage | None = None,
) -> dict[str, Any]:
    host = node_probe_summary.linux_host
    return _compact(
        {
            "reported_phase": (reported_phase or host.reported_phase).value,
            "host_name": host.hostname,
            "os_name": host.os_type,
            "distribution_name": None,
            "kernel_release": host.kernel_release,
            "virtualization_available": None,
            "sudo_available": None,
            "observed_ips": list(host.observed_local_ips),
            "notes": list(host.notes),
            "raw_payload": {
                "linux_host": host.to_dict(),
            },
        }
    )


def build_linux_substrate_probe_write(
    node_probe_summary: NodeProbeSummary,
    *,
    join_complete_payload: JoinCompletePayload | None = None,
    reported_phase: BootstrapStage | None = None,
) -> dict[str, Any]:
    host = node_probe_summary.linux_host
    substrate = node_probe_summary.linux_substrate
    runtime = node_probe_summary.container_runtime
    local_execution = join_complete_payload.local_execution if join_complete_payload else LocalJoinExecution()
    return _compact(
        {
            "reported_phase": (reported_phase or substrate.reported_phase).value,
            "distribution_name": None,
            "kernel_release": host.kernel_release,
            "docker_available": substrate.docker_available,
            "docker_version": substrate.docker_version,
            "wireguard_available": substrate.wireguard_available,
            "gpu_available": None,
            # Backend currently aggregates resource_summary from linux-substrate-probe.
            "cpu_cores": host.cpu_cores,
            "memory_gb": host.memory_gb,
            "disk_free_gb": host.disk_free_gb,
            "observed_ips": _merge_unique(host.observed_local_ips, substrate.observed_local_ips),
            "observed_wireguard_ip": local_execution.observed_wireguard_ip or substrate.observed_wireguard_ip,
            "observed_advertise_addr": local_execution.observed_swarm_advertise_addr
            or runtime.observed_swarm_advertise_addr,
            "observed_data_path_addr": None,
            "notes": list(substrate.notes),
            "raw_payload": {
                "linux_substrate": substrate.to_dict(),
                "linux_host_capacity": _compact(
                    {
                        "cpu_cores": host.cpu_cores,
                        "memory_gb": host.memory_gb,
                        "disk_free_gb": host.disk_free_gb,
                    }
                ),
                "container_runtime_network": _compact(
                    {
                        "observed_swarm_advertise_addr": runtime.observed_swarm_advertise_addr,
                        "swarm_node_id_hint": runtime.swarm_node_id_hint,
                    }
                ),
                "mapping_notes": [
                    "cpu_cores/memory_gb/disk_free_gb are exported here because backend resource_summary reads them from linux-substrate-probe.",
                ],
            },
        }
    )


def build_container_runtime_probe_write(
    node_probe_summary: NodeProbeSummary,
    *,
    reported_phase: BootstrapStage | None = None,
) -> dict[str, Any]:
    runtime = node_probe_summary.container_runtime
    return _compact(
        {
            "reported_phase": (reported_phase or runtime.reported_phase).value,
            "runtime_name": runtime.runtime_name,
            "runtime_version": None,
            "engine_available": runtime.runtime_socket_access,
            "image_store_accessible": None,
            "network_ready": _runtime_network_ready(runtime.swarm_membership_state),
            "observed_images": [],
            "notes": list(runtime.notes),
            "raw_payload": {
                "container_runtime": runtime.to_dict(),
            },
        }
    )


def build_join_complete_write(join_complete_payload: JoinCompletePayload) -> dict[str, Any]:
    local_execution = join_complete_payload.local_execution
    backend_locator = join_complete_payload.backend_locator
    return _compact(
        {
            "reported_phase": local_execution.reported_phase.value,
            "node_ref": backend_locator.node_ref,
            "compute_node_id": backend_locator.compute_node_id,
            "observed_wireguard_ip": local_execution.observed_wireguard_ip,
            "observed_advertise_addr": local_execution.observed_swarm_advertise_addr,
            "observed_data_path_addr": None,
            "notes": [local_execution.detail] if local_execution.detail else [],
            "raw_payload": {
                "local_execution": local_execution.to_dict(),
                "backend_locator": backend_locator.to_dict(),
                "mapping_notes": [
                    "join-complete is exported as backend flat ingress; runtime-local nested blocks stay under raw_payload only.",
                    "node_probe_summary remains runtime-local and is not sent as flat join-complete ingress.",
                ],
            },
        }
    )


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _merge_unique(*value_groups: tuple[str, ...]) -> list[str]:
    merged: list[str] = []
    for values in value_groups:
        for value in values:
            if value not in merged:
                merged.append(value)
    return merged


def _runtime_network_ready(swarm_membership_state: str | None) -> bool | None:
    if swarm_membership_state is None:
        return None
    state = swarm_membership_state.strip().lower()
    if state in {"active", "joined", "ready"}:
        return True
    if state in {"inactive", "left", "failed", "error"}:
        return False
    return None
