from __future__ import annotations

from typing import Any

from seller_client_app.bootstrap.backend_payloads import build_backend_write_payloads
from seller_client_app.bootstrap.phase1 import build_join_complete_payload, build_phase1_plan, build_probe_summary
from seller_client_app.contracts.phase1 import (
    BackendLocatorHint,
    BootstrapStage,
    JoinMaterialEnvelope,
    LocalJoinExecution,
)


def join_material_from_session(session_payload: dict[str, Any]) -> JoinMaterialEnvelope:
    join_material = session_payload.get("swarm_join_material") or {}
    manager_addr = join_material.get("manager_addr")
    manager_port = join_material.get("manager_port")
    swarm_join_command = join_material.get("swarm_join_command")
    if not manager_addr or manager_port is None or not swarm_join_command:
        raise ValueError("Onboarding session is missing the required swarm join material.")

    recommended_compute_node_id = (
        join_material.get("recommended_compute_node_id") or session_payload.get("requested_compute_node_id")
    )
    required_labels = dict(session_payload.get("required_labels") or join_material.get("recommended_labels") or {})
    expected_wireguard_ip = session_payload.get("expected_wireguard_ip")
    return JoinMaterialEnvelope(
        join_session_id=str(session_payload["session_id"]),
        seller_user_id=str(session_payload["seller_user_id"]),
        manager_addr=str(manager_addr),
        manager_port=int(manager_port),
        swarm_join_command=str(swarm_join_command),
        requested_offer_tier=session_payload.get("requested_offer_tier"),
        requested_accelerator=session_payload.get("requested_accelerator"),
        recommended_compute_node_id=recommended_compute_node_id,
        expected_swarm_advertise_addr=expected_wireguard_ip,
        expected_wireguard_ip=expected_wireguard_ip,
        required_labels=required_labels,
        registry_host=join_material.get("registry_host"),
        registry_port=join_material.get("registry_port"),
    )


def build_phase1_drafts_from_session(session_payload: dict[str, Any]) -> dict[str, Any]:
    join_input = join_material_from_session(session_payload)
    probe_summary = build_probe_summary(join_input)
    join_complete_payload = build_join_complete_payload(
        join_input,
        probe_summary,
        local_execution=LocalJoinExecution(reported_phase=BootstrapStage.INSTALL),
        backend_locator=BackendLocatorHint(
            compute_node_id=join_input.recommended_compute_node_id,
            required_labels=dict(join_input.required_labels),
        ),
    )
    return {
        "join_input": join_input.to_dict(),
        "phase1_plan": build_phase1_plan(join_input).to_dict(),
        "probe_summary": probe_summary.to_dict(),
        "write_payloads": build_backend_write_payloads(
            probe_summary,
            join_complete_payload=join_complete_payload,
        ),
    }


def summarize_onboarding_session(session_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if session_payload is None:
        return None
    return {
        "session_id": session_payload.get("session_id"),
        "seller_user_id": session_payload.get("seller_user_id"),
        "status": session_payload.get("status"),
        "requested_accelerator": session_payload.get("requested_accelerator"),
        "requested_compute_node_id": session_payload.get("requested_compute_node_id"),
        "expected_wireguard_ip": session_payload.get("expected_wireguard_ip"),
        "manager_acceptance": session_payload.get("manager_acceptance") or {},
        "effective_target_addr": session_payload.get("effective_target_addr"),
        "effective_target_source": session_payload.get("effective_target_source"),
        "truth_authority": session_payload.get("truth_authority"),
        "minimum_tcp_validation": session_payload.get("minimum_tcp_validation") or {},
        "probe_summary": session_payload.get("probe_summary") or {},
        "container_runtime_probe": session_payload.get("container_runtime_probe") or {},
        "last_join_complete": session_payload.get("last_join_complete") or {},
    }
