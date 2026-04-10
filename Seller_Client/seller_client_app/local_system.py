from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import httpx

from seller_client_app.config import Settings, get_settings


_SCRIPT_CAPABILITY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "tool_name": "inspect_environment_health",
        "legacy_tool_names": ("run_environment_check",),
        "display_name": "Inspect Environment Health",
        "kind": "inspect",
        "implementation_surface": "python_wrapper",
        "summary": "Collect local Windows, WSL, Docker, backend, and seller-client health into a structured report.",
        "recommended_for": ("preflight", "diagnostics", "repair_triage"),
        "backing_scripts": ("bootstrap/windows/check_windows_overlay_runtime.ps1",),
    },
    {
        "tool_name": "repair_environment_health",
        "legacy_tool_names": ("run_semi_auto_repair",),
        "display_name": "Repair Environment Health",
        "kind": "repair",
        "implementation_surface": "python_wrapper",
        "summary": "Run the semi-automatic local repair path, then refresh the structured health report.",
        "recommended_for": ("repair", "bootstrap"),
        "backing_scripts": (),
    },
    {
        "tool_name": "inspect_overlay_runtime",
        "legacy_tool_names": ("run_overlay_runtime_check",),
        "display_name": "Inspect Overlay Runtime",
        "kind": "inspect",
        "implementation_surface": "powershell_script",
        "summary": "Inspect the Windows WireGuard tunnel, Docker Desktop runtime, and overlay reachability.",
        "recommended_for": ("network", "preflight", "swarm_debug"),
        "backing_scripts": ("bootstrap/windows/check_windows_overlay_runtime.ps1",),
    },
    {
        "tool_name": "inspect_network_path",
        "legacy_tool_names": ("check_network_environment",),
        "display_name": "Inspect Network Path",
        "kind": "inspect",
        "implementation_surface": "python_wrapper",
        "summary": "Summarize WireGuard routes, manager reachability, and Docker Swarm connectivity for the current session target.",
        "recommended_for": ("network", "preflight", "join_validation"),
        "backing_scripts": ("bootstrap/windows/check_windows_overlay_runtime.ps1",),
    },
    {
        "tool_name": "prepare_machine_wireguard",
        "legacy_tool_names": ("prepare_machine_wireguard_config",),
        "display_name": "Prepare Machine WireGuard",
        "kind": "prepare",
        "implementation_surface": "python_wrapper",
        "summary": "Prepare the machine-specific WireGuard config in the standard cache path for this computer.",
        "recommended_for": ("identity", "join_preparation"),
        "backing_scripts": (),
    },
    {
        "tool_name": "execute_join_workflow",
        "legacy_tool_names": ("run_standard_join_workflow",),
        "display_name": "Execute Join Workflow",
        "kind": "execute",
        "implementation_surface": "powershell_script",
        "summary": "Run the controlled Windows seller join workflow using backend-issued manager truth and WireGuard addresses.",
        "recommended_for": ("join", "repair", "narrow_execution"),
        "backing_scripts": (
            "bootstrap/windows/attempt_manager_addr_correction_cycle.ps1",
            "bootstrap/windows/rejoin_windows_swarm_worker.ps1",
            "bootstrap/windows/recover_docker_desktop_engine.ps1",
            "bootstrap/windows/capture_repair_state.ps1",
            "bootstrap/windows/swarm_runtime_common.ps1",
            "bootstrap/windows/monitor_swarm_manager_truth.ps1",
        ),
    },
    {
        "tool_name": "execute_guided_join",
        "legacy_tool_names": ("run_guided_join_assessment",),
        "display_name": "Execute Guided Join",
        "kind": "execute",
        "implementation_surface": "composite_workflow",
        "summary": "Prepare machine identity, inspect the environment, execute the join workflow, refresh backend truth, and verify manager-side task execution.",
        "recommended_for": ("join", "natural_language_default", "end_to_end"),
        "backing_scripts": (
            "bootstrap/windows/check_windows_overlay_runtime.ps1",
            "bootstrap/windows/attempt_manager_addr_correction_cycle.ps1",
            "bootstrap/windows/rejoin_windows_swarm_worker.ps1",
            "bootstrap/windows/recover_docker_desktop_engine.ps1",
            "bootstrap/windows/capture_repair_state.ps1",
            "bootstrap/windows/swarm_runtime_common.ps1",
            "bootstrap/windows/monitor_swarm_manager_truth.ps1",
            "bootstrap/windows/probe_swarm_manager_task_execution.ps1",
        ),
    },
    {
        "tool_name": "verify_manager_task",
        "legacy_tool_names": ("verify_manager_task_execution",),
        "display_name": "Verify Manager Task",
        "kind": "verify",
        "implementation_surface": "powershell_script",
        "summary": "Confirm from the manager side that the selected worker has a Running task. This is the seller-join completion standard.",
        "recommended_for": ("join_validation", "completion_standard"),
        "backing_scripts": (
            "bootstrap/windows/probe_swarm_manager_task_execution.ps1",
            "bootstrap/windows/monitor_swarm_manager_truth.ps1",
            "bootstrap/windows/swarm_runtime_common.ps1",
        ),
    },
    {
        "tool_name": "start_local_service",
        "legacy_tool_names": (),
        "display_name": "Start Local Service",
        "kind": "start",
        "implementation_surface": "python_process",
        "summary": "Start the local seller client loopback service and wait for the root page to respond.",
        "recommended_for": ("local_ui", "operator_support"),
        "backing_scripts": (),
    },
    {
        "tool_name": "verify_local_service_content",
        "legacy_tool_names": ("retest_local_content",),
        "display_name": "Verify Local Service Content",
        "kind": "verify",
        "implementation_surface": "python_wrapper",
        "summary": "Recheck one or more local seller client HTTP paths without using them as the swarm-join completion standard.",
        "recommended_for": ("local_ui", "content_probe"),
        "backing_scripts": (),
    },
    {
        "tool_name": "cleanup_join_state",
        "legacy_tool_names": ("clear_join_state",),
        "display_name": "Cleanup Join State",
        "kind": "cleanup",
        "implementation_surface": "powershell_script",
        "summary": "Leave Docker Swarm locally, optionally refresh backend truth, and clear persisted runtime evidence.",
        "recommended_for": ("reset", "retry", "cleanup"),
        "backing_scripts": (
            "bootstrap/windows/clear_windows_join_state.ps1",
            "bootstrap/windows/swarm_runtime_common.ps1",
        ),
    },
    {
        "tool_name": "stop_local_service_and_cleanup",
        "legacy_tool_names": ("stop_join_and_cleanup",),
        "display_name": "Stop Local Service And Cleanup",
        "kind": "cleanup",
        "implementation_surface": "composite_workflow",
        "summary": "Stop the local seller client listener, leave the current swarm join state, optionally refresh backend truth, and clear runtime evidence.",
        "recommended_for": ("reset", "retry", "operator_cleanup"),
        "backing_scripts": (
            "bootstrap/windows/clear_windows_join_state.ps1",
            "bootstrap/windows/swarm_runtime_common.ps1",
        ),
    },
)

SCRIPT_TOOL_ALIASES: dict[str, str] = {
    legacy_name: spec["tool_name"]
    for spec in _SCRIPT_CAPABILITY_SPECS
    for legacy_name in spec["legacy_tool_names"]
}


def canonical_script_tool_name(name: str) -> str:
    return SCRIPT_TOOL_ALIASES.get(str(name or "").strip(), str(name or "").strip())


def list_script_capabilities(settings: Settings) -> dict[str, Any]:
    script_root = settings.project_root / "bootstrap" / "windows"
    capability_entries: list[dict[str, Any]] = []
    script_to_capabilities: dict[str, list[str]] = {}

    for spec in _SCRIPT_CAPABILITY_SPECS:
        backing_scripts: list[dict[str, Any]] = []
        for relative_path in spec["backing_scripts"]:
            absolute_path = settings.project_root / relative_path
            normalized_relative = relative_path.replace("\\", "/")
            backing_scripts.append(
                {
                    "relative_path": normalized_relative,
                    "path": str(absolute_path),
                    "exists": absolute_path.exists(),
                }
            )
            script_to_capabilities.setdefault(normalized_relative, []).append(str(spec["tool_name"]))

        capability_entries.append(
            {
                "tool_name": spec["tool_name"],
                "legacy_tool_names": list(spec["legacy_tool_names"]),
                "display_name": spec["display_name"],
                "kind": spec["kind"],
                "implementation_surface": spec["implementation_surface"],
                "summary": spec["summary"],
                "recommended_for": list(spec["recommended_for"]),
                "backing_scripts": backing_scripts,
            }
        )

    internal_scripts: list[dict[str, Any]] = []
    if script_root.exists():
        for script_path in sorted(script_root.glob("*.ps1")):
            relative_path = str(script_path.relative_to(settings.project_root)).replace("\\", "/")
            exposed_via = script_to_capabilities.get(relative_path, [])
            internal_scripts.append(
                {
                    "relative_path": relative_path,
                    "path": str(script_path),
                    "exists": script_path.exists(),
                    "status": "ai_supported" if exposed_via else "internal_only",
                    "exposed_via": exposed_via,
                }
            )

    return {
        "catalog_version": "2026-04-10",
        "generated_at": _timestamp(),
        "naming_convention": "inspect_* / prepare_* / execute_* / verify_* / cleanup_* / start_* / stop_*",
        "recommended_join_sequence": [
            "list_script_capabilities",
            "refresh_onboarding_session",
            "read_join_material",
            "prepare_machine_wireguard",
            "execute_guided_join",
        ],
        "capabilities": capability_entries,
        "internal_scripts": internal_scripts,
    }


def collect_environment_health(
    settings: Settings,
    *,
    expected_wireguard_ip: str | None = None,
    repair: bool = False,
    local_app_port: int | None = None,
    overlay_sample_count: int = 3,
    overlay_interval_seconds: int = 1,
) -> dict[str, Any]:
    report_path = settings.health_root_path / "latest-health-report.json"
    repair_actions: list[str] = []
    if repair:
        repair_actions = _apply_local_repairs(settings)

    overlay_runtime = run_overlay_runtime_check(
        settings,
        local_app_port=local_app_port,
        overlay_sample_count=overlay_sample_count,
        overlay_interval_seconds=overlay_interval_seconds,
    )
    overlay_payload = overlay_runtime.get("payload") if overlay_runtime.get("ok") else None

    report = {
        "captured_at": _timestamp(),
        "repair_requested": repair,
        "repair_actions": repair_actions,
        "report_path": str(report_path),
        "system": _collect_system_section(),
        "python_runtime": _collect_python_runtime_section(settings),
        "codex": _collect_codex_section(settings),
        "wsl": _collect_wsl_section(settings),
        "wireguard": _collect_wireguard_section(settings, overlay_payload, expected_wireguard_ip),
        "docker": _collect_docker_section(settings, overlay_payload),
        "backend_connectivity": _collect_backend_connectivity_section(settings),
        "seller_client_runtime": _collect_seller_client_runtime_section(
            settings,
            overlay_payload,
            report_path=report_path,
            local_app_port=local_app_port,
        ),
    }
    report["summary"] = _build_health_summary(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def run_overlay_runtime_check(
    settings: Settings,
    *,
    local_app_port: int | None = None,
    overlay_sample_count: int = 3,
    overlay_interval_seconds: int = 1,
) -> dict[str, Any]:
    script_path = settings.project_root / "bootstrap" / "windows" / "check_windows_overlay_runtime.ps1"
    if not script_path.exists():
        return {
            "ok": False,
            "step": "overlay_runtime_check",
            "error": f"script_not_found: {script_path}",
            "payload": None,
        }
    if platform.system() != "Windows":
        return {
            "ok": False,
            "step": "overlay_runtime_check",
            "error": "windows_only",
            "payload": None,
        }

    completed = _run_process(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-HostTunnelName",
            settings.windows_wireguard_tunnel_name,
            "-LocalAppPort",
            str(local_app_port or settings.app_port),
            "-ManagerWireGuardAddress",
            settings.manager_wireguard_address,
            "-ManagerPublicAddress",
            settings.manager_public_address,
            "-ManagerSshPort",
            str(settings.manager_ssh_port),
            "-UbuntuDistro",
            settings.windows_ubuntu_distro,
            "-DockerDesktopSoakSampleCount",
            str(max(1, overlay_sample_count)),
            "-DockerDesktopSoakIntervalSeconds",
            str(max(0, overlay_interval_seconds)),
        ],
        timeout_seconds=max(20, overlay_sample_count * max(1, overlay_interval_seconds) + 20),
    )
    payload = _parse_json_blob(completed["stdout"]) or _parse_json_blob(completed["combined"])
    return {
        "ok": completed["ok"] and isinstance(payload, dict),
        "step": "overlay_runtime_check",
        "error": None if completed["ok"] else completed["combined"],
        "command": completed["command"],
        "exit_code": completed["exit_code"],
        "stdout": completed["stdout"],
        "stderr": completed["stderr"],
        "payload": payload if isinstance(payload, dict) else None,
    }


def prepare_machine_wireguard_config(
    settings: Settings,
    *,
    source_path: str | None = None,
    expected_wireguard_ip: str | None = None,
    overwrite_cache: bool = False,
) -> dict[str, Any]:
    target_path = settings.wireguard_runtime_config_path
    source_candidates = _wireguard_config_source_candidates(settings, explicit_source=source_path)
    selected_source: Path | None = None
    selected_inspection: dict[str, Any] | None = None

    target_inspection = _inspect_wireguard_config_file(target_path, expected_wireguard_ip=expected_wireguard_ip)
    if target_inspection["valid"] and not overwrite_cache:
        return {
            "ok": True,
            "status": "already_prepared",
            "checked_at": _timestamp(),
            "target_path": str(target_path),
            "source_path": str(target_path),
            "expected_wireguard_ip": expected_wireguard_ip,
            "source_candidates": [str(path) for path in source_candidates],
            "inspection": target_inspection,
        }

    candidate_reports: list[dict[str, Any]] = []
    for candidate in source_candidates:
        inspection = _inspect_wireguard_config_file(candidate, expected_wireguard_ip=expected_wireguard_ip)
        candidate_reports.append(inspection)
        if inspection["valid"]:
            selected_source = candidate
            selected_inspection = inspection
            break

    if selected_source is None or selected_inspection is None:
        explicit_invalid = bool(source_path)
        return {
            "ok": False,
            "status": "invalid_source" if explicit_invalid else "missing_machine_wireguard_config",
            "checked_at": _timestamp(),
            "target_path": str(target_path),
            "source_path": str(Path(source_path).expanduser()) if source_path else None,
            "expected_wireguard_ip": expected_wireguard_ip,
            "source_candidates": [str(path) for path in source_candidates],
            "candidate_reports": candidate_reports,
            "error": "wireguard_config_invalid" if explicit_invalid else "machine_wireguard_config_missing",
            "guidance": (
                "Provide the machine-specific WireGuard config with source_path or SELLER_CLIENT_WG_CONFIG_PATH, "
                f"or place it at {target_path} before retrying the join."
            ),
        }

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if selected_source.resolve() != target_path.resolve() or overwrite_cache:
        target_path.write_text(selected_source.read_text(encoding="utf-8"), encoding="utf-8")

    final_inspection = _inspect_wireguard_config_file(target_path, expected_wireguard_ip=expected_wireguard_ip)
    return {
        "ok": bool(final_inspection["valid"]),
        "status": "prepared" if selected_source.resolve() != target_path.resolve() else "already_prepared",
        "checked_at": _timestamp(),
        "target_path": str(target_path),
        "source_path": str(selected_source),
        "expected_wireguard_ip": expected_wireguard_ip,
        "source_candidates": [str(path) for path in source_candidates],
        "candidate_reports": candidate_reports,
        "inspection": final_inspection,
        "error": None if final_inspection["valid"] else "wireguard_config_cache_invalid",
    }


def run_standard_join_workflow(
    settings: Settings,
    *,
    session_file: str,
    join_mode: str = "wireguard",
    advertise_address: str | None = None,
    data_path_address: str | None = None,
    listen_address: str | None = None,
    wireguard_config_path: str | None = None,
    minimum_tcp_validation_port: int | None = None,
    post_join_probe_count: int | None = None,
    probe_interval_seconds: int | None = None,
    manager_probe_count: int | None = None,
    manager_probe_interval_seconds: int | None = None,
) -> dict[str, Any]:
    script_path = settings.project_root / "bootstrap" / "windows" / "attempt_manager_addr_correction_cycle.ps1"
    if not script_path.exists():
        return {
            "ok": False,
            "step": "standard_join_workflow",
            "error": f"script_not_found: {script_path}",
            "payload": None,
        }
    if platform.system() != "Windows":
        return {
            "ok": False,
            "step": "standard_join_workflow",
            "error": "windows_only",
            "payload": None,
        }
    session_manager_addr, session_target_error = _resolve_session_manager_addr(session_file)
    if session_target_error is not None:
        return {
            "ok": False,
            "step": "standard_join_workflow",
            "error": session_target_error,
            "payload": None,
        }

    expected_ip = advertise_address or settings.default_expected_wireguard_ip or settings.manager_wireguard_address
    wireguard_config_preparation = None
    if str(join_mode or "").strip().lower() == "wireguard":
        wireguard_config_preparation = prepare_machine_wireguard_config(
            settings,
            source_path=wireguard_config_path,
            expected_wireguard_ip=expected_ip,
        )
        if not wireguard_config_preparation.get("ok"):
            return {
                "ok": False,
                "step": "standard_join_workflow",
                "error": str(wireguard_config_preparation.get("error") or "machine_wireguard_config_missing"),
                "payload": None,
                "wireguard_config_preparation": wireguard_config_preparation,
            }

    listen = listen_address or f"{expected_ip}:2377"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-SessionFilePath",
        session_file,
        "-JoinMode",
        join_mode,
        "-ManagerWireGuardAddress",
        session_manager_addr,
        "-AdvertiseAddress",
        expected_ip,
        "-DataPathAddress",
        data_path_address or expected_ip,
        "-ListenAddress",
        listen,
        "-ManagerHostName",
        settings.manager_public_address,
        "-ManagerSshPort",
        str(settings.manager_ssh_port),
        "-ManagerMonitorUbuntuDistro",
        settings.windows_ubuntu_distro,
    ]
    if post_join_probe_count is not None:
        command += ["-PostJoinProbeCount", str(max(0, post_join_probe_count))]
    if probe_interval_seconds is not None:
        command += ["-ProbeIntervalSeconds", str(max(0, probe_interval_seconds))]
    if manager_probe_count is not None:
        command += ["-ManagerProbeCount", str(max(0, manager_probe_count))]
    if manager_probe_interval_seconds is not None:
        command += ["-ManagerProbeIntervalSeconds", str(max(0, manager_probe_interval_seconds))]

    completed = _run_process(
        command,
        timeout_seconds=900,
    )
    payload = _parse_json_blob(completed["stdout"]) or _parse_json_blob(completed["combined"])
    return {
        "ok": completed["ok"],
        "step": "standard_join_workflow",
        "command": completed["command"],
        "exit_code": completed["exit_code"],
        "stdout": completed["stdout"],
        "stderr": completed["stderr"],
        "payload": payload if isinstance(payload, dict) else None,
        "wireguard_config_preparation": wireguard_config_preparation,
    }


def verify_manager_task_execution(
    settings: Settings,
    *,
    session_file: str,
    task_probe_timeout_seconds: int = 60,
    task_probe_interval_seconds: int = 3,
    probe_image: str | None = None,
) -> dict[str, Any]:
    script_path = settings.project_root / "bootstrap" / "windows" / "probe_swarm_manager_task_execution.ps1"
    if not script_path.exists():
        return {
            "ok": False,
            "step": "manager_task_execution",
            "error": f"script_not_found: {script_path}",
            "payload": None,
        }
    if platform.system() != "Windows":
        return {
            "ok": False,
            "step": "manager_task_execution",
            "error": "windows_only",
            "payload": None,
        }

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-SessionFilePath",
        session_file,
        "-ManagerHostName",
        settings.manager_public_address,
        "-ManagerSshPort",
        str(settings.manager_ssh_port),
        "-UbuntuDistro",
        settings.windows_ubuntu_distro,
        "-TaskProbeTimeoutSeconds",
        str(max(5, task_probe_timeout_seconds)),
        "-TaskProbeIntervalSeconds",
        str(max(1, task_probe_interval_seconds)),
    ]
    if probe_image:
        command += ["-ProbeImage", probe_image]

    completed = _run_process(command, timeout_seconds=max(120, task_probe_timeout_seconds + 30))
    payload = _parse_json_blob(completed["stdout"]) or _parse_json_blob(completed["combined"])
    verified = bool(isinstance(payload, dict) and payload.get("task_execution_verified"))
    return {
        "ok": completed["ok"] and verified,
        "step": "manager_task_execution",
        "error": None if completed["ok"] else completed["combined"],
        "command": completed["command"],
        "exit_code": completed["exit_code"],
        "stdout": completed["stdout"],
        "stderr": completed["stderr"],
        "payload": payload if isinstance(payload, dict) else None,
    }


def clear_join_state(
    settings: Settings,
    *,
    leave_timeout_seconds: int = 25,
    dry_run: bool = False,
) -> dict[str, Any]:
    script_path = settings.project_root / "bootstrap" / "windows" / "clear_windows_join_state.ps1"
    if not script_path.exists():
        return {
            "ok": False,
            "step": "clear_join_state",
            "error": f"script_not_found: {script_path}",
            "payload": None,
        }
    if platform.system() != "Windows":
        return {
            "ok": False,
            "step": "clear_join_state",
            "error": "windows_only",
            "payload": None,
        }

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-LeaveTimeoutSeconds",
        str(max(1, leave_timeout_seconds)),
    ]
    if dry_run:
        command.append("-DryRun")

    completed = _run_process(command, timeout_seconds=max(30, leave_timeout_seconds + 15))
    payload = _parse_json_blob(completed["stdout"]) or _parse_json_blob(completed["combined"])
    return {
        "ok": completed["ok"] and isinstance(payload, dict) and bool(payload.get("ok", True)),
        "step": "clear_join_state",
        "error": None if completed["ok"] else completed["combined"],
        "command": completed["command"],
        "exit_code": completed["exit_code"],
        "stdout": completed["stdout"],
        "stderr": completed["stderr"],
        "payload": payload if isinstance(payload, dict) else None,
    }


def check_network_environment(
    settings: Settings,
    *,
    session_file: str | None = None,
    expected_wireguard_ip: str | None = None,
    overlay_sample_count: int = 3,
    overlay_interval_seconds: int = 1,
) -> dict[str, Any]:
    health_payload = collect_environment_health(
        settings,
        expected_wireguard_ip=expected_wireguard_ip,
        repair=False,
        local_app_port=settings.app_port,
        overlay_sample_count=overlay_sample_count,
        overlay_interval_seconds=overlay_interval_seconds,
    )
    docker = dict(health_payload.get("docker") or {})
    wireguard = dict(health_payload.get("wireguard") or {})
    swarm_payload = dict(docker.get("swarm") or {})
    remote_managers = [
        str(item.get("Addr"))
        for item in list(swarm_payload.get("RemoteManagers") or [])
        if isinstance(item, dict) and str(item.get("Addr") or "").strip()
    ]
    session_manager_addr, session_manager_port, _ = _resolve_session_manager_target(session_file)
    expected_manager_addr = session_manager_addr or settings.manager_wireguard_address
    expected_manager_port = session_manager_port or 2377
    expected_remote_manager = f"{expected_manager_addr}:{expected_manager_port}"
    local_node_state = str(docker.get("local_node_state") or "").strip()
    local_node_addr = str(docker.get("node_addr") or "").strip() or None
    swarm_connected = local_node_state.lower() == "active" and expected_remote_manager in remote_managers

    return {
        "checked_at": _timestamp(),
        "success_standard": "docker_swarm_connectivity",
        "swarm_connectivity": {
            "verified": swarm_connected,
            "local_node_state": local_node_state or None,
            "local_node_addr": local_node_addr,
            "expected_remote_manager": expected_remote_manager,
            "remote_managers": remote_managers,
            "manager_port_checks": list(wireguard.get("manager_port_checks") or []),
            "route_summary": list(wireguard.get("route_summary") or []),
        },
        "environment": health_payload,
    }


def start_local_service(
    settings: Settings,
    *,
    port: int | None = None,
    startup_timeout_seconds: int = 20,
) -> dict[str, Any]:
    actual_port = int(port or settings.app_port)
    if _is_tcp_listener_open(actual_port):
        probe = retest_local_content(settings, port=actual_port, paths=["/"], timeout_seconds=5)
        return {
            "ok": True,
            "status": "already_running",
            "port": actual_port,
            "content_probe": probe,
        }

    venv_python = _venv_python_path(settings.project_root / ".venv")
    if not venv_python.exists():
        return {
            "ok": False,
            "status": "venv_missing",
            "port": actual_port,
            "error": f"venv_python_missing: {venv_python}",
        }

    logs_dir = settings.workspace_root_path / settings.logs_subdir_name
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"seller-client-{datetime.now(UTC):%Y%m%d%H%M%S}.log"
    command = [
        str(venv_python),
        "-m",
        "uvicorn",
        "seller_client_app.main:app",
        "--host",
        settings.app_host,
        "--port",
        str(actual_port),
    ]
    env = os.environ.copy()
    env["SELLER_CLIENT_BACKEND_BASE_URL"] = settings.backend_base_url
    if settings.codex_config_template_path.exists():
        env["SELLER_CLIENT_CODEX_CONFIG_TEMPLATE_PATH"] = str(settings.codex_config_template_path)

    creationflags = 0
    start_new_session = False
    if platform.system() == "Windows":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess,
            "CREATE_NEW_PROCESS_GROUP",
            0,
        )
    else:
        start_new_session = True

    try:
        with log_path.open("a", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=str(settings.project_root),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
    except OSError as exc:
        return {
            "ok": False,
            "status": "start_failed",
            "port": actual_port,
            "command": command,
            "log_path": str(log_path),
            "error": str(exc),
        }

    probe = _wait_for_local_content(settings, port=actual_port, paths=["/"], timeout_seconds=startup_timeout_seconds)
    return {
        "ok": bool(probe.get("ok")),
        "status": "started" if probe.get("ok") else "started_unverified",
        "port": actual_port,
        "pid": process.pid,
        "command": command,
        "log_path": str(log_path),
        "content_probe": probe,
    }


def retest_local_content(
    settings: Settings,
    *,
    port: int | None = None,
    paths: list[str] | None = None,
    expected_status_code: int = 200,
    expected_substring: str | None = None,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    actual_port = int(port or settings.app_port)
    requested_paths = [path for path in (paths or ["/"]) if str(path).strip()]
    if not requested_paths:
        requested_paths = ["/"]

    results = [
        _probe_local_content(
            actual_port,
            path,
            expected_status_code=expected_status_code,
            expected_substring=expected_substring,
            timeout_seconds=timeout_seconds,
        )
        for path in requested_paths
    ]
    return {
        "ok": all(bool(item.get("ok")) for item in results),
        "port": actual_port,
        "results": results,
    }


def stop_local_service(
    settings: Settings,
    *,
    port: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    actual_port = int(port or settings.app_port)
    listeners = _list_listening_processes(actual_port)
    if listeners is None:
        return {
            "ok": False,
            "status": "listener_inspection_failed",
            "port": actual_port,
        }
    if not listeners:
        return {
            "ok": True,
            "status": "already_stopped",
            "port": actual_port,
            "listeners": [],
        }
    if dry_run:
        return {
            "ok": True,
            "status": "would_stop",
            "port": actual_port,
            "listeners": listeners,
        }

    stop_command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            f"$pids = Get-NetTCPConnection -LocalPort {actual_port} -State Listen -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty OwningProcess -Unique; "
            "foreach ($pid in $pids) { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue }"
        ),
    ]
    completed = _run_process(stop_command, timeout_seconds=20)
    remaining = _list_listening_processes(actual_port)
    return {
        "ok": completed["ok"] and not remaining,
        "status": "stopped" if completed["ok"] and not remaining else "stop_incomplete",
        "port": actual_port,
        "listeners": listeners,
        "remaining_listeners": remaining,
        "command": completed["command"],
        "exit_code": completed["exit_code"],
        "stdout": completed["stdout"],
        "stderr": completed["stderr"],
    }


def export_diagnostics_bundle(
    settings: Settings,
    *,
    runtime_snapshot: dict[str, Any],
    onboarding_session: dict[str, Any] | None,
) -> dict[str, Any]:
    settings.exports_root_path.mkdir(parents=True, exist_ok=True)
    bundle_path = settings.exports_root_path / f"seller-client-diagnostics-{datetime.now(UTC):%Y%m%d%H%M%S}.zip"
    with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "runtime_snapshot.json",
            json.dumps(runtime_snapshot, ensure_ascii=False, indent=2),
        )
        health_path = settings.health_root_path / "latest-health-report.json"
        if health_path.exists():
            archive.write(health_path, arcname="health/latest-health-report.json")

        if onboarding_session is not None:
            session_id = onboarding_session.get("session_id")
            if session_id:
                session_root = settings.workspace_root_path / settings.session_subdir_name / str(session_id)
                if session_root.exists():
                    for file_path in session_root.rglob("*"):
                        if file_path.is_file():
                            archive.write(file_path, arcname=str(Path("session") / file_path.relative_to(session_root)))

    return {
        "bundle_path": str(bundle_path),
        "created_at": _timestamp(),
        "exists": bundle_path.exists(),
        "size_bytes": bundle_path.stat().st_size if bundle_path.exists() else 0,
    }


def _apply_local_repairs(settings: Settings) -> list[str]:
    actions: list[str] = []
    for path in (
        settings.workspace_root_path,
        settings.workspace_root_path / settings.session_subdir_name,
        settings.health_root_path,
        settings.exports_root_path,
    ):
        path.mkdir(parents=True, exist_ok=True)
        actions.append(f"ensured_path:{path}")

    venv_dir = settings.project_root / ".venv"
    venv_python = _venv_python_path(venv_dir)
    bootstrap_python = _resolve_bootstrap_python()
    if not venv_python.exists():
        completed = _run_process([str(bootstrap_python), "-m", "venv", str(venv_dir)], timeout_seconds=240)
        if completed["ok"]:
            actions.append(f"created_venv:{venv_dir}")
        else:
            actions.append(f"venv_create_failed:{completed['combined']}")

    if venv_python.exists():
        pip_upgrade = _run_process([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], timeout_seconds=240)
        actions.append("pip_upgraded" if pip_upgrade["ok"] else f"pip_upgrade_failed:{pip_upgrade['combined']}")
        install = _run_process([str(venv_python), "-m", "pip", "install", "-e", str(settings.project_root)], timeout_seconds=300)
        actions.append("seller_client_installed" if install["ok"] else f"editable_install_failed:{install['combined']}")

    return actions


def _collect_system_section() -> dict[str, Any]:
    return {
        "status": "ok" if platform.system() == "Windows" else "warning",
        "platform": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python_pid": os.getpid(),
    }


def _collect_python_runtime_section(settings: Settings) -> dict[str, Any]:
    venv_dir = settings.project_root / ".venv"
    venv_python = _venv_python_path(venv_dir)
    return {
        "status": "ok" if venv_python.exists() else "warning",
        "current_executable": sys.executable,
        "current_version": sys.version.split()[0],
        "project_root": str(settings.project_root),
        "venv_dir": str(venv_dir),
        "venv_exists": venv_dir.exists(),
        "venv_python": str(venv_python),
        "venv_python_exists": venv_python.exists(),
        "package_metadata_exists": (settings.project_root / "seller_client.egg-info").exists(),
    }


def _collect_codex_section(settings: Settings) -> dict[str, Any]:
    codex_path = shutil.which(settings.codex_command)
    auth_path = settings.codex_auth_source_path
    config_template = settings.codex_config_template_path
    version_result = None
    if codex_path:
        version_result = _run_process([codex_path, "--version"], timeout_seconds=20)

    return {
        "status": "ok" if codex_path and auth_path.exists() and config_template.exists() else "warning",
        "command": settings.codex_command,
        "cli_path": codex_path,
        "cli_available": codex_path is not None,
        "cli_version": None if version_result is None else version_result["stdout"],
        "auth_source_path": str(auth_path),
        "auth_exists": auth_path.exists(),
        "config_template_path": str(config_template),
        "config_template_exists": config_template.exists(),
    }


def _collect_wsl_section(settings: Settings) -> dict[str, Any]:
    wsl_path = shutil.which("wsl.exe")
    if not wsl_path:
        return {
            "status": "warning",
            "wsl_available": False,
            "ubuntu_distro": settings.windows_ubuntu_distro,
            "ubuntu_present": False,
            "distros": "",
        }

    completed = _run_process([wsl_path, "-l", "-v"], timeout_seconds=20)
    stdout = completed["stdout"]
    return {
        "status": "ok" if completed["ok"] and settings.windows_ubuntu_distro.lower() in stdout.lower() else "warning",
        "wsl_available": True,
        "wsl_command": wsl_path,
        "ubuntu_distro": settings.windows_ubuntu_distro,
        "ubuntu_present": settings.windows_ubuntu_distro.lower() in stdout.lower(),
        "distros": stdout,
    }


def _collect_wireguard_section(
    settings: Settings,
    overlay_payload: dict[str, Any] | None,
    expected_wireguard_ip: str | None,
) -> dict[str, Any]:
    service = (overlay_payload or {}).get("wireguard_service") or {}
    windows_overlay = (overlay_payload or {}).get("windows_overlay") or {}
    overlay_addresses = list(windows_overlay.get("overlay_addresses") or [])
    manager_port_checks = list(windows_overlay.get("manager_port_checks") or [])
    expected_ip = expected_wireguard_ip or settings.default_expected_wireguard_ip
    expected_ip_present = bool(
        expected_ip
        and any(str(item.get("IPAddress") or "") == expected_ip for item in overlay_addresses if isinstance(item, dict))
    )
    ports_reachable = all(bool(item.get("reachable")) for item in manager_port_checks) if manager_port_checks else False
    service_running = str(service.get("status") or "").lower() == "running"
    wg_show = str((overlay_payload or {}).get("windows_wireguard") or "").strip()

    return {
        "status": "ok" if service_running and expected_ip_present and ports_reachable else "warning",
        "interface_name": settings.windows_wireguard_tunnel_name,
        "service_running": service_running,
        "service": service,
        "expected_wireguard_ip": expected_ip,
        "expected_wireguard_ip_present": expected_ip_present,
        "manager_wireguard_address": settings.manager_wireguard_address,
        "manager_port_checks": manager_port_checks,
        "route_summary": list(windows_overlay.get("manager_routes") or []),
        "overlay_addresses": overlay_addresses,
        "wg_show": wg_show,
    }


def _collect_docker_section(settings: Settings, overlay_payload: dict[str, Any] | None) -> dict[str, Any]:
    docker_service = (overlay_payload or {}).get("docker_service") or {}
    docker_swarm = (overlay_payload or {}).get("docker_swarm") or {}
    docker_contexts = (overlay_payload or {}).get("docker_contexts") or {}
    swarm_payload = _parse_json_blob(str(docker_swarm.get("stdout") or ""))
    local_node_state = None if not isinstance(swarm_payload, dict) else swarm_payload.get("LocalNodeState")
    node_addr = None if not isinstance(swarm_payload, dict) else swarm_payload.get("NodeAddr")

    return {
        "status": "ok" if docker_swarm.get("exit_code") == 0 else "warning",
        "docker_service": docker_service,
        "docker_cli_available": docker_swarm.get("start_ok", docker_swarm.get("exit_code") == 0),
        "docker_info_available": docker_swarm.get("exit_code") == 0,
        "docker_contexts": docker_contexts,
        "swarm": swarm_payload if isinstance(swarm_payload, dict) else {},
        "local_node_state": local_node_state,
        "node_addr": node_addr,
        "manager_public_address": settings.manager_public_address,
        "docker_desktop": (overlay_payload or {}).get("docker_desktop") or {},
    }


def _collect_backend_connectivity_section(settings: Settings) -> dict[str, Any]:
    url = f"{settings.backend_base_url}{settings.backend_api_prefix}/health"
    try:
        with httpx.Client(timeout=10.0, trust_env=False) as client:
            response = client.get(url)
        payload = response.json() if response.content else {}
        return {
            "status": "ok" if response.is_success else "warning",
            "url": url,
            "reachable": response.is_success,
            "status_code": response.status_code,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "status": "warning",
            "url": url,
            "reachable": False,
            "status_code": None,
            "payload": {},
            "error": str(exc),
        }


def _collect_seller_client_runtime_section(
    settings: Settings,
    overlay_payload: dict[str, Any] | None,
    *,
    report_path: Path,
    local_app_port: int | None,
) -> dict[str, Any]:
    session_root = settings.workspace_root_path / settings.session_subdir_name
    session_count = len([path for path in session_root.iterdir() if path.is_dir()]) if session_root.exists() else 0
    app_listener = (((overlay_payload or {}).get("local_app") or {}).get("listening"))
    root_status = (((overlay_payload or {}).get("local_app") or {}).get("root")) or {}
    return {
        "status": "ok",
        "workspace_root": str(settings.workspace_root_path),
        "session_root": str(session_root),
        "session_count": session_count,
        "health_report_path": str(report_path),
        "exports_root": str(settings.exports_root_path),
        "local_app_port": local_app_port or settings.app_port,
        "local_app_listening": bool(app_listener) if app_listener is not None else _is_tcp_listener_open(local_app_port or settings.app_port),
        "local_app_root": root_status,
    }


def _build_health_summary(report: dict[str, Any]) -> dict[str, Any]:
    sections = [
        "system",
        "python_runtime",
        "codex",
        "wsl",
        "wireguard",
        "docker",
        "backend_connectivity",
        "seller_client_runtime",
    ]
    warnings = [name for name in sections if str(report.get(name, {}).get("status")) != "ok"]
    return {
        "status": "healthy" if not warnings else "needs_attention",
        "sections_checked": sections,
        "warnings": warnings,
    }


def _is_tcp_listener_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _resolve_session_manager_addr(session_file: str) -> tuple[str | None, str | None]:
    manager_addr, _, error = _resolve_session_manager_target(session_file)
    return manager_addr, error


def _resolve_session_manager_target(session_file: str | None) -> tuple[str | None, int | None, str | None]:
    if not session_file:
        return None, None, "session_file_missing"
    try:
        payload = json.loads(Path(session_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None, "session_file_invalid"

    onboarding = payload.get("onboarding_session")
    if not isinstance(onboarding, dict):
        return None, None, "onboarding_session_missing"

    join_material = onboarding.get("swarm_join_material")
    if not isinstance(join_material, dict):
        return None, None, "swarm_join_material_missing"

    manager_addr = str(join_material.get("manager_addr") or "").strip()
    if not manager_addr:
        return None, None, "session_manager_addr_missing"
    manager_port = join_material.get("manager_port")
    try:
        resolved_port = int(manager_port) if manager_port is not None else 2377
    except (TypeError, ValueError):
        resolved_port = 2377

    return manager_addr, resolved_port, None


def _wireguard_config_source_candidates(settings: Settings, *, explicit_source: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    for raw in (
        explicit_source,
        os.getenv("SELLER_CLIENT_WG_CONFIG_PATH"),
        str(settings.wireguard_runtime_config_path),
    ):
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _inspect_wireguard_config_file(path: Path, *, expected_wireguard_ip: str | None = None) -> dict[str, Any]:
    resolved = path.expanduser()
    exists = resolved.exists()
    payload = {
        "path": str(resolved),
        "exists": exists,
        "valid": False,
        "error": None,
        "expected_wireguard_ip": expected_wireguard_ip,
        "matched_expected_wireguard_ip": None,
        "address_entries": [],
        "has_interface_block": False,
        "has_peer_block": False,
        "has_private_key": False,
    }
    if not exists:
        payload["error"] = "file_not_found"
        return payload

    try:
        raw = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        payload["error"] = str(exc)
        return payload

    lines = [line.strip() for line in raw.replace("\r\n", "\n").split("\n")]
    address_entries: list[str] = []
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().lower() == "address":
            address_entries.extend(part.strip() for part in value.split(",") if part.strip())

    payload["address_entries"] = address_entries
    payload["has_interface_block"] = any(line.lower() == "[interface]" for line in lines)
    payload["has_peer_block"] = any(line.lower() == "[peer]" for line in lines)
    payload["has_private_key"] = any(line.lower().startswith("privatekey") and "=" in line for line in lines)
    matched_expected_ip = None
    if expected_wireguard_ip:
        matched_expected_ip = any(
            entry.split("/", 1)[0].strip() == expected_wireguard_ip
            for entry in address_entries
        )
    payload["matched_expected_wireguard_ip"] = matched_expected_ip

    payload["valid"] = bool(
        payload["has_interface_block"]
        and payload["has_peer_block"]
        and payload["has_private_key"]
        and address_entries
        and (matched_expected_ip is not False)
    )
    if not payload["valid"] and payload["error"] is None:
        payload["error"] = "wireguard_config_invalid"
    return payload


def _run_process(command: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "combined": str(exc),
        }
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    combined = "\n".join(part for part in [stdout, stderr] if part).strip()
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "combined": combined,
    }


def _parse_json_blob(text: str) -> dict[str, Any] | list[Any] | None:
    cleaned = (text or "").replace("\x00", "").strip()
    if not cleaned:
        return None
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start >= 0 and end > start:
            candidate = cleaned[start : end + 1]
            try:
                return json.loads(candidate)
            except ValueError:
                continue
    try:
        return json.loads(cleaned)
    except ValueError:
        return None


def _probe_local_content(
    port: int,
    path: str,
    *,
    expected_status_code: int = 200,
    expected_substring: str | None = None,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    normalized_path = str(path or "/").strip() or "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    url = f"http://127.0.0.1:{port}{normalized_path}"
    try:
        with httpx.Client(timeout=float(timeout_seconds), follow_redirects=True, trust_env=False) as client:
            response = client.get(url)
        body = response.text
        ok = response.status_code == expected_status_code
        if expected_substring is not None:
            ok = ok and expected_substring in body
        return {
            "ok": ok,
            "path": normalized_path,
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "expected_status_code": expected_status_code,
            "expected_substring": expected_substring,
            "matched_expected_substring": None if expected_substring is None else expected_substring in body,
            "body_snippet": body[:200],
        }
    except Exception as exc:
        return {
            "ok": False,
            "path": normalized_path,
            "url": url,
            "status_code": None,
            "content_type": None,
            "expected_status_code": expected_status_code,
            "expected_substring": expected_substring,
            "matched_expected_substring": False if expected_substring is not None else None,
            "body_snippet": "",
            "error": str(exc),
        }


def _wait_for_local_content(
    settings: Settings,
    *,
    port: int,
    paths: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    last_result = retest_local_content(settings, port=port, paths=paths, timeout_seconds=5)
    while not last_result.get("ok") and time.monotonic() < deadline:
        time.sleep(1)
        last_result = retest_local_content(settings, port=port, paths=paths, timeout_seconds=5)
    return last_result


def _list_listening_processes(port: int) -> list[dict[str, Any]] | None:
    if platform.system() != "Windows":
        return []

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            f"$records = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty OwningProcess -Unique | "
            "ForEach-Object { "
            '$proc = Get-CimInstance Win32_Process -Filter "ProcessId = $_" -ErrorAction SilentlyContinue; '
            "[PSCustomObject]@{ pid = [int]$_; name = $proc.Name; command_line = $proc.CommandLine } "
            "}; "
            "$records | ConvertTo-Json -Depth 4 -Compress"
        ),
    ]
    completed = _run_process(command, timeout_seconds=20)
    if not completed["ok"] and not completed["stdout"]:
        return None
    payload = _parse_json_blob(completed["stdout"]) or _parse_json_blob(completed["combined"])
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _resolve_bootstrap_python() -> Path:
    candidates = [Path(sys.executable)]
    for command in ("python", "py"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("Unable to locate a Python interpreter for seller client bootstrap.")


def _venv_python_path(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect or repair the local seller client environment health report.")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--expected-wireguard-ip", default=None)
    parser.add_argument("--overlay-sample-count", type=int, default=3)
    parser.add_argument("--overlay-interval-seconds", type=int, default=1)
    args = parser.parse_args()

    payload = collect_environment_health(
        get_settings(),
        expected_wireguard_ip=args.expected_wireguard_ip,
        repair=args.repair,
        overlay_sample_count=args.overlay_sample_count,
        overlay_interval_seconds=args.overlay_interval_seconds,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
