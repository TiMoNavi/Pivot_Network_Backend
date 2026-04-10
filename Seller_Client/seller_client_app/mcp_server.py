from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from dataclasses import replace
from pathlib import Path
from typing import Any

from seller_client_app.backend import BackendClient
from seller_client_app.config import get_settings
from seller_client_app.local_system import (
    canonical_script_tool_name,
    check_network_environment,
    clear_join_state as perform_clear_join_state,
    collect_environment_health,
    export_diagnostics_bundle,
    list_script_capabilities,
    prepare_machine_wireguard_config,
    run_overlay_runtime_check,
    run_standard_join_workflow,
    retest_local_content,
    start_local_service,
    stop_local_service,
    verify_manager_task_execution,
)
from seller_client_app.onboarding import build_phase1_drafts_from_session, summarize_onboarding_session
from seller_client_app.state import (
    append_correction_evidence,
    normalize_runtime_evidence,
    run_minimum_tcp_validation as perform_minimum_tcp_validation,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-file", type=str, default=os.getenv("SELLER_CLIENT_SESSION_FILE"))
    return parser.parse_args()


def _load_session_context(session_file: str | None) -> dict[str, Any]:
    if not session_file:
        raise RuntimeError("SELLER_CLIENT_SESSION_FILE is not set.")
    return json.loads(Path(session_file).read_text(encoding="utf-8"))


def _save_session_context(session_file: str | None, payload: dict[str, Any]) -> None:
    if not session_file:
        raise RuntimeError("SELLER_CLIENT_SESSION_FILE is not set.")
    path = Path(session_file)
    temp_path = path.with_name(f"{path.name}.{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _log_file_path(session_file: str | None) -> Path | None:
    if not session_file:
        return None
    path = Path(session_file)
    try:
        logs_dir = path.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return logs_dir / "mcp-server.log"


def _append_mcp_log(session_file: str | None, message: str) -> None:
    log_path = _log_file_path(session_file)
    if log_path is None:
        return
    timestamp = datetime.now(UTC).isoformat()
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
    except OSError:
        return


def _backend_client(payload: dict[str, Any]) -> BackendClient:
    settings = replace(
        get_settings(),
        backend_base_url=payload.get("backend_base_url") or get_settings().backend_base_url,
        backend_api_prefix=payload.get("backend_api_prefix") or get_settings().backend_api_prefix,
    )
    return BackendClient(settings, token=payload.get("auth_token"))


def _write_message(message: dict[str, Any]) -> None:
    body = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _read_message() -> dict[str, Any] | None:
    header_bytes = bytearray()
    while True:
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            if not header_bytes:
                return None
            raise RuntimeError("Unexpected EOF while reading MCP headers.")
        header_bytes.extend(chunk)
        if (
            header_bytes.endswith(b"\r\n\r\n")
            or header_bytes.endswith(b"\n\n")
            or header_bytes.endswith(b"\r\r")
        ):
            break
        if len(header_bytes) > 64 * 1024:
            raise RuntimeError("MCP header block exceeded 64 KiB.")

    header_text = header_bytes.decode("utf-8", errors="replace")
    headers: dict[str, str] = {}
    for line in header_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        key, value = stripped.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = bytearray()
    while len(body) < length:
        chunk = sys.stdin.buffer.read(length - len(body))
        if not chunk:
            raise RuntimeError("Unexpected EOF while reading MCP body.")
        body.extend(chunk)
    return json.loads(body.decode("utf-8"))


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload if isinstance(payload, dict) else {"result": payload},
        "isError": is_error,
    }


def _canonical_tool_name(name: str) -> str:
    return canonical_script_tool_name(name)


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_script_capabilities",
            "description": "Return the AI-facing local script capability directory, including canonical tool names, legacy aliases, and internal-only PowerShell dependencies.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "read_environment_health",
            "description": "Read the last persisted local environment health snapshot for this seller client session.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "inspect_environment_health",
            "description": "Collect and persist the local Windows, WSL, Docker, backend, and seller-client health report.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "expected_wireguard_ip": {"type": "string"},
                    "overlay_sample_count": {"type": "integer"},
                    "overlay_interval_seconds": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "repair_environment_health",
            "description": "Run the semi-automatic local repair/install flow and persist the refreshed health report for this session.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "expected_wireguard_ip": {"type": "string"},
                    "overlay_sample_count": {"type": "integer"},
                    "overlay_interval_seconds": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "inspect_overlay_runtime",
            "description": "Inspect the Windows WireGuard tunnel, Docker Desktop runtime, and overlay reachability through the controlled script surface.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "overlay_sample_count": {"type": "integer"},
                    "overlay_interval_seconds": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "inspect_network_path",
            "description": "Check the WireGuard route, manager port reachability, and Docker Swarm connectivity using the current session target.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "expected_wireguard_ip": {"type": "string"},
                    "overlay_sample_count": {"type": "integer"},
                    "overlay_interval_seconds": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "prepare_machine_wireguard",
            "description": "Prepare the machine-specific WireGuard config in the standard cache path so the controlled Windows join workflow can bootstrap Docker Desktop with the correct seller identity on this computer.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_path": {"type": "string"},
                    "expected_wireguard_ip": {"type": "string"},
                    "overwrite_cache": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "execute_join_workflow",
            "description": "Execute the controlled Windows standard join workflow using the current onboarding session file. Success is judged by Docker Swarm connectivity and manager truth.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "join_mode": {"type": "string"},
                    "advertise_address": {"type": "string"},
                    "data_path_address": {"type": "string"},
                    "listen_address": {"type": "string"},
                    "wireguard_config_path": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "execute_guided_join",
            "description": "Run the guided seller join assessment: prepare the machine WireGuard config, inspect local environment, read join material, check overlay runtime, execute the standard join workflow, refresh backend truth, verify manager-side task execution, and summarize join effects using manager task execution as the completion standard.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "join_mode": {"type": "string"},
                    "expected_wireguard_ip": {"type": "string"},
                    "wireguard_config_path": {"type": "string"},
                    "overlay_sample_count": {"type": "integer"},
                    "overlay_interval_seconds": {"type": "integer"},
                    "post_join_probe_count": {"type": "integer"},
                    "probe_interval_seconds": {"type": "integer"},
                    "manager_probe_count": {"type": "integer"},
                    "manager_probe_interval_seconds": {"type": "integer"},
                    "task_probe_timeout_seconds": {"type": "integer"},
                    "task_probe_interval_seconds": {"type": "integer"},
                    "task_probe_image": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "verify_manager_task",
            "description": "Verify the seller node from the manager side by confirming the worker has a Running task, or by creating a short-lived probe service when needed. This is the completion standard for seller join verification.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_probe_timeout_seconds": {"type": "integer"},
                    "task_probe_interval_seconds": {"type": "integer"},
                    "task_probe_image": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "cleanup_join_state",
            "description": "Clear the local Windows seller join state: leave Docker swarm if joined, optionally refresh backend session, optionally refresh local environment health, and reset persisted local join evidence.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "leave_timeout_seconds": {"type": "integer"},
                    "dry_run": {"type": "boolean"},
                    "refresh_onboarding_session": {"type": "boolean"},
                    "close_onboarding_session": {"type": "boolean"},
                    "run_environment_check_after_clear": {"type": "boolean"},
                    "expected_wireguard_ip": {"type": "string"},
                    "overlay_sample_count": {"type": "integer"},
                    "overlay_interval_seconds": {"type": "integer"},
                    "clear_runtime_evidence": {"type": "boolean"},
                    "clear_last_assistant_run": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "start_local_service",
            "description": "Start the local seller client service on the configured loopback port and wait for the root page to respond.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer"},
                    "startup_timeout_seconds": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "verify_local_service_content",
            "description": "Recheck the local seller client HTTP content on one or more paths without treating it as the join success criterion.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "expected_status_code": {"type": "integer"},
                    "expected_substring": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "stop_local_service_and_cleanup",
            "description": "Stop the local seller service listener, leave the current Docker Swarm join state, optionally refresh backend truth, and clear persisted runtime state.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer"},
                    "stop_local_service": {"type": "boolean"},
                    "leave_timeout_seconds": {"type": "integer"},
                    "dry_run": {"type": "boolean"},
                    "refresh_onboarding_session": {"type": "boolean"},
                    "close_onboarding_session": {"type": "boolean"},
                    "run_environment_check_after_clear": {"type": "boolean"},
                    "expected_wireguard_ip": {"type": "string"},
                    "overlay_sample_count": {"type": "integer"},
                    "overlay_interval_seconds": {"type": "integer"},
                    "clear_runtime_evidence": {"type": "boolean"},
                    "clear_last_assistant_run": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "export_diagnostics_bundle",
            "description": "Export the current runtime snapshot, health report, and session artifacts into a diagnostic zip bundle.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "list_compute_options",
            "description": "Return the locally supported accelerator and offer-tier options together with the current onboarding request, if any.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "read_onboarding_state",
            "description": "Read the current seller onboarding session state, manager acceptance, and local browser session metadata.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "read_join_material",
            "description": "Read the current backend-issued swarm join material, required labels, and expected WireGuard identity.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "refresh_onboarding_session",
            "description": "Refresh the onboarding session from the backend and persist the latest state into the local session file.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "generate_phase1_probe_drafts",
            "description": "Generate phase-1 probe and join-complete draft payloads from the current onboarding session contract.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "submit_linux_host_probe",
            "description": "Submit the Linux host probe using the existing backend seller onboarding contract.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reported_phase": {"type": "string"},
                    "host_name": {"type": "string"},
                    "os_name": {"type": "string"},
                    "distribution_name": {"type": "string"},
                    "kernel_release": {"type": "string"},
                    "virtualization_available": {"type": "boolean"},
                    "sudo_available": {"type": "boolean"},
                    "observed_ips": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "array", "items": {"type": "string"}},
                    "raw_payload": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "submit_linux_substrate_probe",
            "description": "Submit the Linux substrate probe without exposing free shell access.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reported_phase": {"type": "string"},
                    "distribution_name": {"type": "string"},
                    "kernel_release": {"type": "string"},
                    "docker_available": {"type": "boolean"},
                    "docker_version": {"type": "string"},
                    "wireguard_available": {"type": "boolean"},
                    "gpu_available": {"type": "boolean"},
                    "cpu_cores": {"type": "integer"},
                    "memory_gb": {"type": "integer"},
                    "disk_free_gb": {"type": "integer"},
                    "observed_ips": {"type": "array", "items": {"type": "string"}},
                    "observed_wireguard_ip": {"type": "string"},
                    "observed_advertise_addr": {"type": "string"},
                    "observed_data_path_addr": {"type": "string"},
                    "notes": {"type": "array", "items": {"type": "string"}},
                    "raw_payload": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "submit_container_runtime_probe",
            "description": "Submit the container runtime probe using the controlled onboarding write surface.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reported_phase": {"type": "string"},
                    "runtime_name": {"type": "string"},
                    "runtime_version": {"type": "string"},
                    "engine_available": {"type": "boolean"},
                    "image_store_accessible": {"type": "boolean"},
                    "network_ready": {"type": "boolean"},
                    "observed_images": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "array", "items": {"type": "string"}},
                    "raw_payload": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "submit_join_complete",
            "description": "Submit the flat join-complete ingress required by the backend. Do not send nested runtime-only payloads.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reported_phase": {"type": "string"},
                    "node_ref": {"type": "string"},
                    "compute_node_id": {"type": "string"},
                    "observed_wireguard_ip": {"type": "string"},
                    "observed_advertise_addr": {"type": "string"},
                    "observed_data_path_addr": {"type": "string"},
                    "notes": {"type": "array", "items": {"type": "string"}},
                    "raw_payload": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "record_runtime_correction",
            "description": "Persist local correction evidence only. This does not change backend truth or claim manager acceptance.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "correction_kind": {"type": "string"},
                    "outcome": {"type": "string"},
                    "reported_phase": {"type": "string"},
                    "join_mode": {"type": "string"},
                    "target_host": {"type": "string"},
                    "target_port": {"type": "integer"},
                    "observed_wireguard_ip": {"type": "string"},
                    "observed_advertise_addr": {"type": "string"},
                    "observed_data_path_addr": {"type": "string"},
                    "manager_node_addr_hint": {"type": "string"},
                    "script_path": {"type": "string"},
                    "log_path": {"type": "string"},
                    "rollback_path": {"type": "string"},
                    "notes": {"type": "array", "items": {"type": "string"}},
                    "raw_payload": {"type": "object"},
                },
                "required": ["correction_kind", "outcome"],
                "additionalProperties": False,
            },
        },
        {
            "name": "run_minimum_tcp_validation",
            "description": "Run the local minimum TCP validation against a seller target and persist the probe result only.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "host": {"type": "string"},
                    "port": {"type": "integer"},
                    "timeout_ms": {"type": "integer"},
                    "validation_kind": {"type": "string"},
                    "source": {"type": "string"},
                    "target_label": {"type": "string"},
                    "notes": {"type": "array", "items": {"type": "string"}},
                    "raw_payload": {"type": "object"},
                },
                "required": ["host", "port"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_local_container",
            "description": "Create a local Docker container through a controlled docker create/start surface without exposing arbitrary shell execution.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "image": {"type": "string"},
                    "name": {"type": "string"},
                    "command": {"type": "array", "items": {"type": "string"}},
                    "env": {"type": "object", "additionalProperties": {"type": "string"}},
                    "labels": {"type": "object", "additionalProperties": {"type": "string"}},
                    "publish_ports": {"type": "array", "items": {"type": "string"}},
                    "start_after_create": {"type": "boolean"},
                },
                "required": ["image"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_local_containers",
            "description": "List local Docker containers through docker ps in a machine-readable format.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "all": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "reset_runtime_state",
            "description": "Clear local runtime evidence and optionally close the current onboarding session on the backend.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "close_onboarding_session": {"type": "boolean"},
                    "clear_runtime_evidence": {"type": "boolean"},
                    "clear_last_assistant_run": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "close_onboarding_session",
            "description": "Close the seller onboarding session from the backend and persist the final state.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


def _list_compute_options(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    onboarding = payload.get("onboarding_session") or {}
    join_material = onboarding.get("swarm_join_material") or {}
    return {
        "supported_accelerators": list(settings.supported_accelerators),
        "supported_offer_tiers": list(settings.supported_offer_tiers),
        "current_request": {
            "requested_accelerator": onboarding.get("requested_accelerator"),
            "requested_offer_tier": onboarding.get("requested_offer_tier"),
            "requested_compute_node_id": onboarding.get("requested_compute_node_id"),
        },
        "backend_recommendation": {
            "recommended_compute_node_id": join_material.get("recommended_compute_node_id"),
            "claim_required": join_material.get("claim_required"),
            "expected_wireguard_ip": onboarding.get("expected_wireguard_ip"),
        },
    }


def _read_join_material(onboarding: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": onboarding.get("session_id"),
        "requested_accelerator": onboarding.get("requested_accelerator"),
        "requested_offer_tier": onboarding.get("requested_offer_tier"),
        "requested_compute_node_id": onboarding.get("requested_compute_node_id"),
        "expected_wireguard_ip": onboarding.get("expected_wireguard_ip"),
        "effective_target_addr": onboarding.get("effective_target_addr"),
        "effective_target_source": onboarding.get("effective_target_source"),
        "truth_authority": onboarding.get("truth_authority"),
        "minimum_tcp_validation": dict(onboarding.get("minimum_tcp_validation") or {}),
        "swarm_join_material": dict(onboarding.get("swarm_join_material") or {}),
        "required_labels": dict(onboarding.get("required_labels") or {}),
        "manager_acceptance": dict(onboarding.get("manager_acceptance") or {}),
    }


def _run_docker_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"docker command unavailable: {exc}") from exc

    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "docker command failed")
    return completed


def _create_local_container(arguments: dict[str, Any]) -> dict[str, Any]:
    image = str(arguments.get("image") or "").strip()
    if not image:
        raise RuntimeError("image is required")

    command = ["create"]
    name = str(arguments.get("name") or "").strip()
    if name:
        command += ["--name", name]

    for key, value in dict(arguments.get("env") or {}).items():
        command += ["-e", f"{key}={value}"]
    for key, value in dict(arguments.get("labels") or {}).items():
        command += ["--label", f"{key}={value}"]
    for publish in list(arguments.get("publish_ports") or []):
        command += ["-p", str(publish)]

    command.append(image)
    command.extend(str(item) for item in list(arguments.get("command") or []))

    created = _run_docker_command(command)
    container_id = (created.stdout or "").strip().splitlines()[-1]

    started = False
    if bool(arguments.get("start_after_create")):
        _run_docker_command(["start", container_id])
        started = True

    inspected = _run_docker_command(["inspect", container_id])
    inspect_payload = json.loads(inspected.stdout or "[]")
    inspect_item = inspect_payload[0] if inspect_payload else {}
    state = inspect_item.get("State") or {}
    config = inspect_item.get("Config") or {}

    return {
        "container_id": container_id,
        "name": inspect_item.get("Name") or name,
        "image": config.get("Image") or image,
        "created": True,
        "started": started,
        "status": state.get("Status"),
        "running": state.get("Running"),
        "ports": inspect_item.get("NetworkSettings", {}).get("Ports") or {},
    }


def _list_local_containers(arguments: dict[str, Any]) -> dict[str, Any]:
    docker_args = ["ps", "--format", "{{json .}}"]
    if bool(arguments.get("all")):
        docker_args.insert(1, "-a")
    completed = _run_docker_command(docker_args)
    containers: list[dict[str, Any]] = []
    for line in (completed.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        containers.append(json.loads(line))
    return {"containers": containers}


def _invoke_tool(name: str, arguments: dict[str, Any], payload: dict[str, Any], session_file: str | None) -> dict[str, Any]:
    name = _canonical_tool_name(name)
    onboarding = payload.get("onboarding_session")
    backend = _backend_client(payload)
    settings = get_settings()

    if name == "list_script_capabilities":
        return list_script_capabilities(settings)

    if name == "list_compute_options":
        return _list_compute_options(payload)

    if name == "read_onboarding_state":
        return {
            "current_user": payload.get("current_user"),
            "window_session": payload.get("window_session"),
            "onboarding_session": summarize_onboarding_session(onboarding),
            "runtime_evidence": normalize_runtime_evidence(payload.get("runtime_evidence")),
            "local_health_snapshot": payload.get("local_health_snapshot"),
            "last_runtime_workflow": payload.get("last_runtime_workflow"),
            "last_assistant_run": payload.get("last_assistant_run"),
        }

    if name == "read_environment_health":
        return {
            "local_health_snapshot": payload.get("local_health_snapshot"),
            "report_path": str(settings.health_root_path / "latest-health-report.json"),
        }

    if name in {"inspect_environment_health", "repair_environment_health"}:
        health_payload = collect_environment_health(
            settings,
            expected_wireguard_ip=arguments.get("expected_wireguard_ip")
            or ((onboarding or {}).get("expected_wireguard_ip"))
            or settings.default_expected_wireguard_ip,
            repair=name == "repair_environment_health",
            local_app_port=settings.app_port,
            overlay_sample_count=int(arguments.get("overlay_sample_count") or 3),
            overlay_interval_seconds=int(arguments.get("overlay_interval_seconds") or 1),
        )
        payload["local_health_snapshot"] = health_payload
        _save_session_context(session_file, payload)
        return {"local_health_snapshot": health_payload}

    if name == "execute_guided_join":
        return _run_guided_join_assessment(arguments, payload, session_file)

    if name == "inspect_overlay_runtime":
        result = run_overlay_runtime_check(
            settings,
            local_app_port=settings.app_port,
            overlay_sample_count=int(arguments.get("overlay_sample_count") or 3),
            overlay_interval_seconds=int(arguments.get("overlay_interval_seconds") or 1),
        )
        payload["last_runtime_workflow"] = {
            "kind": "overlay_runtime_check",
            "result": result,
        }
        _save_session_context(session_file, payload)
        return payload["last_runtime_workflow"]

    if name == "inspect_network_path":
        result = check_network_environment(
            settings,
            session_file=session_file,
            expected_wireguard_ip=arguments.get("expected_wireguard_ip")
            or ((onboarding or {}).get("expected_wireguard_ip"))
            or settings.default_expected_wireguard_ip,
            overlay_sample_count=int(arguments.get("overlay_sample_count") or 3),
            overlay_interval_seconds=int(arguments.get("overlay_interval_seconds") or 1),
        )
        payload["local_health_snapshot"] = result.get("environment")
        payload["last_runtime_workflow"] = {
            "kind": "inspect_network_path",
            "checked_at": datetime.now(UTC).isoformat(),
            "result": result,
        }
        _save_session_context(session_file, payload)
        return result

    if name == "prepare_machine_wireguard":
        result = prepare_machine_wireguard_config(
            settings,
            source_path=arguments.get("source_path"),
            expected_wireguard_ip=arguments.get("expected_wireguard_ip")
            or ((onboarding or {}).get("expected_wireguard_ip"))
            or settings.default_expected_wireguard_ip,
            overwrite_cache=bool(arguments.get("overwrite_cache", False)),
        )
        payload["last_runtime_workflow"] = {
            "kind": "prepare_machine_wireguard",
            "ran_at": datetime.now(UTC).isoformat(),
            "result": result,
        }
        _save_session_context(session_file, payload)
        return result

    if name == "start_local_service":
        result = start_local_service(
            settings,
            port=int(arguments.get("port") or settings.app_port),
            startup_timeout_seconds=int(arguments.get("startup_timeout_seconds") or 20),
        )
        payload["last_runtime_workflow"] = {
            "kind": "start_local_service",
            "ran_at": datetime.now(UTC).isoformat(),
            "result": result,
        }
        _save_session_context(session_file, payload)
        return result

    if name == "verify_local_service_content":
        result = retest_local_content(
            settings,
            port=int(arguments.get("port") or settings.app_port),
            paths=list(arguments.get("paths") or ["/"]),
            expected_status_code=int(arguments.get("expected_status_code") or 200),
            expected_substring=arguments.get("expected_substring"),
            timeout_seconds=int(arguments.get("timeout_seconds") or 5),
        )
        payload["last_runtime_workflow"] = {
            "kind": "verify_local_service_content",
            "ran_at": datetime.now(UTC).isoformat(),
            "result": result,
        }
        _save_session_context(session_file, payload)
        return result

    if name == "verify_manager_task":
        result = verify_manager_task_execution(
            settings,
            session_file=session_file or "",
            task_probe_timeout_seconds=int(arguments.get("task_probe_timeout_seconds") or 60),
            task_probe_interval_seconds=int(arguments.get("task_probe_interval_seconds") or 3),
            probe_image=arguments.get("task_probe_image"),
        )
        payload["last_runtime_workflow"] = {
            "kind": "verify_manager_task",
            "ran_at": datetime.now(UTC).isoformat(),
            "result": result,
        }
        _save_session_context(session_file, payload)
        return result

    if name == "stop_local_service_and_cleanup":
        local_service_stop = None
        if bool(arguments.get("stop_local_service", True)):
            local_service_stop = stop_local_service(
                settings,
                port=int(arguments.get("port") or settings.app_port),
                dry_run=bool(arguments.get("dry_run")),
            )

        clear_result = perform_clear_join_state(
            settings,
            leave_timeout_seconds=int(arguments.get("leave_timeout_seconds") or 25),
            dry_run=bool(arguments.get("dry_run")),
        )
        backend_sync = {"attempted": False, "status": "skipped", "reason": None}
        overlay_sample_count = int(arguments.get("overlay_sample_count") or 2)
        overlay_interval_seconds = int(arguments.get("overlay_interval_seconds") or 1)
        health_payload = payload.get("local_health_snapshot")
        if bool(arguments.get("run_environment_check_after_clear", True)):
            health_payload = collect_environment_health(
                settings,
                expected_wireguard_ip=arguments.get("expected_wireguard_ip")
                or ((onboarding or {}).get("expected_wireguard_ip"))
                or settings.default_expected_wireguard_ip,
                repair=False,
                local_app_port=settings.app_port,
                overlay_sample_count=overlay_sample_count,
                overlay_interval_seconds=overlay_interval_seconds,
            )
            payload["local_health_snapshot"] = health_payload

        auth_token = str(payload.get("auth_token") or "").strip()
        session_id = str((onboarding or {}).get("session_id") or "").strip()
        if auth_token and session_id:
            if bool(arguments.get("close_onboarding_session")):
                updated = backend.close_onboarding_session(session_id)
                payload["onboarding_session"] = updated
                backend_sync = {"attempted": True, "status": "closed", "reason": None}
            elif bool(arguments.get("refresh_onboarding_session", True)):
                updated = backend.get_onboarding_session(session_id)
                payload["onboarding_session"] = updated
                backend_sync = {"attempted": True, "status": "refreshed", "reason": None}
        elif bool(arguments.get("close_onboarding_session")) or bool(arguments.get("refresh_onboarding_session", True)):
            backend_sync = {"attempted": False, "status": "skipped", "reason": "auth_required_or_session_missing"}

        if bool(arguments.get("clear_runtime_evidence", True)):
            payload["runtime_evidence"] = normalize_runtime_evidence(None)
        if bool(arguments.get("clear_last_assistant_run", True)):
            payload["last_assistant_run"] = None
        payload["last_runtime_workflow"] = {
            "kind": "stop_local_service_and_cleanup",
            "ran_at": datetime.now(UTC).isoformat(),
            "result": {
                "local_service_stop": local_service_stop,
                "clear_join_state": clear_result,
                "backend_sync": backend_sync,
            },
        }
        _save_session_context(session_file, payload)
        return {
            "local_service_stop": local_service_stop,
            "cleanup_join_state": clear_result,
            "clear_join_state": clear_result,
            "backend_sync": backend_sync,
            "local_health_snapshot": health_payload,
            "onboarding_session": summarize_onboarding_session(payload.get("onboarding_session")),
            "runtime_evidence": normalize_runtime_evidence(payload.get("runtime_evidence")),
            "last_runtime_workflow": payload.get("last_runtime_workflow"),
            "last_assistant_run": payload.get("last_assistant_run"),
        }

    if name == "export_diagnostics_bundle":
        bundle = export_diagnostics_bundle(
            settings,
            runtime_snapshot={
                "current_user": payload.get("current_user"),
                "window_session": payload.get("window_session"),
                "onboarding_session": payload.get("onboarding_session"),
                "runtime_evidence": normalize_runtime_evidence(payload.get("runtime_evidence")),
                "local_health_snapshot": payload.get("local_health_snapshot"),
                "last_runtime_workflow": payload.get("last_runtime_workflow"),
                "last_assistant_run": payload.get("last_assistant_run"),
            },
            onboarding_session=onboarding if isinstance(onboarding, dict) else None,
        )
        return bundle

    if name == "list_local_containers":
        return _list_local_containers(arguments)

    if name == "create_local_container":
        return _create_local_container(arguments)

    if onboarding is None:
        raise RuntimeError("Onboarding session is not initialized.")

    session_id = str(onboarding.get("session_id") or "")
    if not session_id:
        raise RuntimeError("Onboarding session id is missing.")

    if name == "read_join_material":
        return _read_join_material(onboarding)

    if name == "execute_join_workflow":
        result = run_standard_join_workflow(
            settings,
            session_file=session_file or "",
            join_mode=str(arguments.get("join_mode") or "wireguard"),
            advertise_address=arguments.get("advertise_address") or onboarding.get("expected_wireguard_ip"),
            data_path_address=arguments.get("data_path_address") or onboarding.get("expected_wireguard_ip"),
            listen_address=arguments.get("listen_address"),
            wireguard_config_path=arguments.get("wireguard_config_path"),
        )
        payload["last_runtime_workflow"] = {
            "kind": "execute_join_workflow",
            "workflow": result,
            "result": result,
        }
        refreshed = backend.get_onboarding_session(session_id)
        payload["onboarding_session"] = refreshed
        _save_session_context(session_file, payload)
        return {
            "last_runtime_workflow": payload["last_runtime_workflow"],
            "onboarding_session": summarize_onboarding_session(refreshed),
        }

    if name == "cleanup_join_state":
        clear_result = perform_clear_join_state(
            settings,
            leave_timeout_seconds=int(arguments.get("leave_timeout_seconds") or 25),
            dry_run=bool(arguments.get("dry_run")),
        )
        backend_sync = {"attempted": False, "status": "skipped", "reason": None}
        overlay_sample_count = int(arguments.get("overlay_sample_count") or 2)
        overlay_interval_seconds = int(arguments.get("overlay_interval_seconds") or 1)
        health_payload = payload.get("local_health_snapshot")
        if bool(arguments.get("run_environment_check_after_clear", True)):
            health_payload = collect_environment_health(
                settings,
                expected_wireguard_ip=arguments.get("expected_wireguard_ip")
                or onboarding.get("expected_wireguard_ip")
                or settings.default_expected_wireguard_ip,
                repair=False,
                local_app_port=settings.app_port,
                overlay_sample_count=overlay_sample_count,
                overlay_interval_seconds=overlay_interval_seconds,
            )
            payload["local_health_snapshot"] = health_payload

        auth_token = str(payload.get("auth_token") or "").strip()
        if auth_token:
            if bool(arguments.get("close_onboarding_session")):
                updated = backend.close_onboarding_session(session_id)
                payload["onboarding_session"] = updated
                backend_sync = {"attempted": True, "status": "closed", "reason": None}
            elif bool(arguments.get("refresh_onboarding_session", True)):
                updated = backend.get_onboarding_session(session_id)
                payload["onboarding_session"] = updated
                backend_sync = {"attempted": True, "status": "refreshed", "reason": None}
        elif bool(arguments.get("close_onboarding_session")) or bool(arguments.get("refresh_onboarding_session", True)):
            backend_sync = {"attempted": False, "status": "skipped", "reason": "auth_required"}

        if bool(arguments.get("clear_runtime_evidence", True)):
            payload["runtime_evidence"] = normalize_runtime_evidence(None)
        if bool(arguments.get("clear_last_assistant_run", True)):
            payload["last_assistant_run"] = None
        payload["last_runtime_workflow"] = {
            "kind": "cleanup_join_state",
            "ran_at": datetime.now(UTC).isoformat(),
            "result": clear_result,
        }
        _save_session_context(session_file, payload)
        return {
            "cleanup_join_state": clear_result,
            "clear_join_state": clear_result,
            "backend_sync": backend_sync,
            "local_health_snapshot": health_payload,
            "onboarding_session": summarize_onboarding_session(payload.get("onboarding_session")),
            "runtime_evidence": normalize_runtime_evidence(payload.get("runtime_evidence")),
            "last_runtime_workflow": payload.get("last_runtime_workflow"),
            "last_assistant_run": payload.get("last_assistant_run"),
        }

    if name == "refresh_onboarding_session":
        updated = backend.get_onboarding_session(session_id)
        payload["onboarding_session"] = updated
        _save_session_context(session_file, payload)
        return summarize_onboarding_session(updated) or {}

    if name == "generate_phase1_probe_drafts":
        return build_phase1_drafts_from_session(onboarding)

    if name == "submit_linux_host_probe":
        updated = backend.submit_linux_host_probe(session_id, _compact(arguments))
        payload["onboarding_session"] = updated
        _save_session_context(session_file, payload)
        return summarize_onboarding_session(updated) or {}

    if name == "submit_linux_substrate_probe":
        updated = backend.submit_linux_substrate_probe(session_id, _compact(arguments))
        payload["onboarding_session"] = updated
        _save_session_context(session_file, payload)
        return summarize_onboarding_session(updated) or {}

    if name == "submit_container_runtime_probe":
        updated = backend.submit_container_runtime_probe(session_id, _compact(arguments))
        payload["onboarding_session"] = updated
        _save_session_context(session_file, payload)
        return summarize_onboarding_session(updated) or {}

    if name == "submit_join_complete":
        updated = backend.submit_join_complete(session_id, _compact(arguments))
        payload["onboarding_session"] = updated
        _save_session_context(session_file, payload)
        return summarize_onboarding_session(updated) or {}

    if name == "record_runtime_correction":
        runtime_evidence, record = append_correction_evidence(payload.get("runtime_evidence"), _compact(arguments))
        payload["runtime_evidence"] = runtime_evidence
        _save_session_context(session_file, payload)
        return {"correction": record, "runtime_evidence": runtime_evidence}

    if name == "run_minimum_tcp_validation":
        runtime_evidence, record = perform_minimum_tcp_validation(payload.get("runtime_evidence"), _compact(arguments))
        payload["runtime_evidence"] = runtime_evidence
        _save_session_context(session_file, payload)
        return {"validation": record, "runtime_evidence": runtime_evidence}

    if name == "reset_runtime_state":
        if bool(arguments.get("close_onboarding_session")):
            updated = backend.close_onboarding_session(session_id)
            payload["onboarding_session"] = updated
        if arguments.get("clear_runtime_evidence", True):
            payload["runtime_evidence"] = normalize_runtime_evidence(None)
        if arguments.get("clear_last_assistant_run", True):
            payload["last_assistant_run"] = None
        _save_session_context(session_file, payload)
        return {
            "status": "reset",
            "onboarding_session": summarize_onboarding_session(payload.get("onboarding_session")),
            "runtime_evidence": normalize_runtime_evidence(payload.get("runtime_evidence")),
            "last_assistant_run": payload.get("last_assistant_run"),
        }

    if name == "close_onboarding_session":
        updated = backend.close_onboarding_session(session_id)
        payload["onboarding_session"] = updated
        _save_session_context(session_file, payload)
        return summarize_onboarding_session(updated) or {}

    raise RuntimeError(f"Unknown tool: {name}")


def _run_guided_join_assessment(
    arguments: dict[str, Any],
    payload: dict[str, Any],
    session_file: str | None,
) -> dict[str, Any]:
    onboarding = payload.get("onboarding_session")
    if not isinstance(onboarding, dict):
        raise RuntimeError("Onboarding session is not initialized.")
    session_id = str(onboarding.get("session_id") or "").strip()
    if not session_id:
        raise RuntimeError("Onboarding session id is missing.")

    settings = get_settings()
    backend = _backend_client(payload)
    refreshed_before_join = backend.get_onboarding_session(session_id)
    payload["onboarding_session"] = refreshed_before_join
    onboarding = refreshed_before_join
    expected_wireguard_ip = (
        arguments.get("expected_wireguard_ip")
        or onboarding.get("expected_wireguard_ip")
        or settings.default_expected_wireguard_ip
    )
    wireguard_config_result = prepare_machine_wireguard_config(
        settings,
        source_path=arguments.get("wireguard_config_path"),
        expected_wireguard_ip=expected_wireguard_ip,
        overwrite_cache=bool(arguments.get("overwrite_cache", False)),
    )
    overlay_sample_count = int(arguments.get("overlay_sample_count") or 2)
    overlay_interval_seconds = int(arguments.get("overlay_interval_seconds") or 1)

    health_payload = collect_environment_health(
        settings,
        expected_wireguard_ip=expected_wireguard_ip,
        repair=False,
        local_app_port=settings.app_port,
        overlay_sample_count=overlay_sample_count,
        overlay_interval_seconds=overlay_interval_seconds,
    )
    payload["local_health_snapshot"] = health_payload

    join_material = _read_join_material(onboarding)

    overlay_result = _overlay_runtime_from_health(health_payload)

    if wireguard_config_result.get("ok"):
        workflow_result = run_standard_join_workflow(
            settings,
            session_file=session_file or "",
            join_mode=str(arguments.get("join_mode") or "wireguard"),
            advertise_address=onboarding.get("expected_wireguard_ip") or expected_wireguard_ip,
            data_path_address=onboarding.get("expected_wireguard_ip") or expected_wireguard_ip,
            listen_address=None,
            wireguard_config_path=wireguard_config_result.get("target_path"),
            post_join_probe_count=int(arguments.get("post_join_probe_count") or 8),
            probe_interval_seconds=int(arguments.get("probe_interval_seconds") or 1),
            manager_probe_count=int(arguments.get("manager_probe_count") or 4),
            manager_probe_interval_seconds=int(arguments.get("manager_probe_interval_seconds") or 2),
        )
    else:
        workflow_result = {
            "ok": False,
            "step": "standard_join_workflow",
            "error": str(wireguard_config_result.get("error") or "machine_wireguard_config_missing"),
            "payload": None,
            "wireguard_config_preparation": wireguard_config_result,
        }

    payload["last_runtime_workflow"] = {
        "kind": "execute_guided_join",
        "workflow": workflow_result,
        "result": workflow_result,
    }

    refreshed = backend.get_onboarding_session(session_id)
    payload["onboarding_session"] = refreshed

    if workflow_result.get("ok"):
        manager_task_execution = verify_manager_task_execution(
            settings,
            session_file=session_file or "",
            task_probe_timeout_seconds=int(arguments.get("task_probe_timeout_seconds") or 60),
            task_probe_interval_seconds=int(arguments.get("task_probe_interval_seconds") or 3),
            probe_image=arguments.get("task_probe_image"),
        )
    else:
        manager_task_execution = {
            "ok": False,
            "step": "manager_task_execution",
            "error": "skipped_until_join_succeeds",
            "payload": {
                "completion_standard": "manager_task_execution",
                "task_execution_verified": False,
                "status": "skipped",
                "reason": "join_workflow_not_successful",
            },
        }
    payload["last_runtime_workflow"]["wireguard_config_preparation"] = wireguard_config_result
    payload["last_runtime_workflow"]["manager_task_execution"] = manager_task_execution

    _save_session_context(session_file, payload)

    assessment = {
        "wireguard_config_preparation": wireguard_config_result,
        "environment": {
            "summary": dict(health_payload.get("summary") or {}),
            "docker": dict(health_payload.get("docker") or {}),
            "wireguard": dict(health_payload.get("wireguard") or {}),
            "backend_connectivity": dict(health_payload.get("backend_connectivity") or {}),
        },
        "join_material": join_material,
        "overlay_runtime": overlay_result,
        "join_workflow": workflow_result,
        "manager_task_execution": manager_task_execution,
        "refreshed_onboarding_session": summarize_onboarding_session(refreshed) or {},
        "join_effect": _summarize_join_effect(workflow_result, refreshed, manager_task_execution),
    }
    return assessment


def _summarize_join_effect(
    workflow_result: dict[str, Any],
    refreshed_onboarding: dict[str, Any],
    manager_task_execution: dict[str, Any],
) -> dict[str, Any]:
    local_join = _extract_local_join_layer(workflow_result)
    manager_acceptance = dict(refreshed_onboarding.get("manager_acceptance") or {})
    workflow_summary = dict((workflow_result.get("payload") or {}).get("summary") or {})
    backend_target = {
        "effective_target_addr": refreshed_onboarding.get("effective_target_addr"),
        "effective_target_source": refreshed_onboarding.get("effective_target_source"),
        "truth_authority": refreshed_onboarding.get("truth_authority"),
        "session_status": refreshed_onboarding.get("status"),
    }
    task_payload = dict(manager_task_execution.get("payload") or {})
    return {
        "success_standard": "manager_task_execution",
        "swarm_connectivity": {
            "verified": workflow_summary.get("swarm_connectivity_verified"),
            "local_swarm_active": workflow_summary.get("local_swarm_active"),
            "manager_acceptance_matched": workflow_summary.get("manager_acceptance_matched"),
            "path_outcome": workflow_summary.get("path_outcome"),
        },
        "manager_task_execution": {
            "verified": manager_task_execution.get("ok"),
            "status": task_payload.get("status"),
            "proof_source": task_payload.get("proof_source"),
            "selected_node_id": ((task_payload.get("selected_candidate") or {}).get("id")),
        },
        "local_join": local_join,
        "manager_raw_truth": {
            "status": manager_acceptance.get("status"),
            "observed_manager_node_addr": manager_acceptance.get("observed_manager_node_addr"),
            "matched": manager_acceptance.get("matched"),
            "detail": manager_acceptance.get("detail"),
        },
        "backend_authoritative_target": backend_target,
    }


def _extract_local_join_layer(workflow_result: dict[str, Any]) -> dict[str, Any]:
    payload = workflow_result.get("payload") or {}
    join_result = payload.get("join_result") or {}
    after_state_raw = join_result.get("after_state")
    after_state: dict[str, Any] = {}
    if isinstance(after_state_raw, str) and after_state_raw.strip():
        try:
            parsed = json.loads(after_state_raw)
            if isinstance(parsed, dict):
                after_state = parsed
        except ValueError:
            after_state = {}
    elif isinstance(after_state_raw, dict):
        after_state = dict(after_state_raw)
    return {
        "ok": workflow_result.get("ok"),
        "path_outcome": ((payload.get("summary") or {}).get("path_outcome")) if isinstance(payload, dict) else None,
        "local_node_state": after_state.get("LocalNodeState"),
        "local_node_id": after_state.get("NodeID"),
        "local_node_addr": after_state.get("NodeAddr"),
        "join_idempotent_reason": join_result.get("join_idempotent_reason"),
    }


def _overlay_runtime_from_health(health_payload: dict[str, Any]) -> dict[str, Any]:
    summary = dict(health_payload.get("summary") or {})
    wireguard = dict(health_payload.get("wireguard") or {})
    docker = dict(health_payload.get("docker") or {})
    return {
        "ok": summary.get("status") in {"healthy", "ok"} or bool(wireguard) or bool(docker),
        "source": "environment_health_snapshot",
        "payload": {
            "wireguard_service": dict(wireguard.get("service") or {}),
            "windows_overlay": {
                "manager_port_checks": list(wireguard.get("manager_port_checks") or []),
                "manager_routes": list(wireguard.get("route_summary") or []),
                "overlay_addresses": list(wireguard.get("overlay_addresses") or []),
                "wg_show": wireguard.get("wg_show"),
            },
            "docker_swarm": {
                "local_node_state": docker.get("local_node_state"),
                "node_addr": docker.get("node_addr"),
                "swarm": dict(docker.get("swarm") or {}),
            },
        },
    }


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def main() -> None:
    args = _parse_args()
    session_file = args.session_file
    _append_mcp_log(session_file, "mcp_server_start")
    while True:
        message = _read_message()
        if message is None:
            _append_mcp_log(session_file, "mcp_server_stop eof")
            return
        method = message.get("method")
        params = message.get("params") or {}
        message_id = message.get("id")
        _append_mcp_log(session_file, f"recv method={method} id={message_id}")

        if method == "initialize":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "seller-client-tools", "version": "0.2.0"},
                    },
                }
            )
            _append_mcp_log(session_file, "sent initialize")
            continue

        if method == "notifications/initialized":
            _append_mcp_log(session_file, "recv initialized_notification")
            continue

        if method == "ping":
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": {}})
            _append_mcp_log(session_file, "sent ping")
            continue

        if method == "tools/list":
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": {"tools": _tool_descriptors()}})
            _append_mcp_log(session_file, "sent tools_list")
            continue

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            _append_mcp_log(session_file, f"tools_call name={name}")
            try:
                payload = _load_session_context(session_file)
                result = _invoke_tool(name, arguments, payload, session_file)
                body = _tool_result(result, is_error=False)
                _append_mcp_log(session_file, f"tools_call_ok name={name}")
            except Exception as exc:
                body = _tool_result({"error": str(exc)}, is_error=True)
                _append_mcp_log(session_file, f"tools_call_error name={name} error={exc}")
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": body})
            continue

        _write_message(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )
        _append_mcp_log(session_file, f"method_not_found method={method}")


if __name__ == "__main__":
    main()
