from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from seller_client_app.active_codex_session import (
    active_codex_session_pointer_path,
    clear_active_codex_session_pointer,
    write_active_codex_session_pointer,
)
from seller_client_app.config import Settings
from seller_client_app.state import SellerClientState, SessionRuntimePaths


class CodexSessionError(Exception):
    pass


_PROMPT_MAX_STATE_JSON_CHARS = 6000
_PROMPT_MAX_STRING_CHARS = 240
_PROMPT_MAX_LIST_ITEMS = 5


def prepare_codex_session(
    *,
    settings: Settings,
    state: SellerClientState,
    session_id: str,
) -> SessionRuntimePaths:
    paths = state.session_paths(session_id)
    paths.codex_dotdir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.workspace_dir.mkdir(parents=True, exist_ok=True)

    config_template = settings.codex_config_template_path
    auth_source = settings.codex_auth_source_path
    if not config_template.exists():
        raise CodexSessionError(f"Missing Codex config template: {config_template}")
    if not auth_source.exists():
        raise CodexSessionError(f"Missing Codex auth source: {auth_source}")

    (paths.codex_dotdir / "config.toml").write_text(config_template.read_text(encoding="utf-8"), encoding="utf-8")
    (paths.codex_dotdir / "auth.json").write_text(auth_source.read_text(encoding="utf-8"), encoding="utf-8")
    cap_sid_source = auth_source.parent / "cap_sid"
    if cap_sid_source.exists():
        (paths.codex_dotdir / "cap_sid").write_text(cap_sid_source.read_text(encoding="utf-8"), encoding="utf-8")

    session_file = state.write_session_runtime_file()
    if session_file is None:
        raise CodexSessionError("Onboarding session is not initialized.")
    write_active_codex_session_pointer(settings, paths)
    try:
        _register_mcp_server(settings, paths)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexSessionError(f"failed to register MCP server: {exc}") from exc
    return paths


def run_codex_assistant(
    *,
    settings: Settings,
    state: SellerClientState,
    session_id: str,
    user_message: str,
) -> dict[str, Any]:
    session_payload = state.current_onboarding_session()
    if session_payload is None:
        raise CodexSessionError("Onboarding session is not initialized.")

    paths = prepare_codex_session(settings=settings, state=state, session_id=session_id)
    output_file = paths.logs_dir / "assistant-last-message.txt"
    prompt = _build_assistant_prompt(state.runtime_snapshot(), user_message)
    env = _codex_env(settings, paths)
    command = _codex_command(settings) + [
        "exec",
        "--skip-git-repo-check",
        "-s",
        settings.codex_exec_sandbox,
        "--cd",
        str(paths.workspace_dir),
        "--color",
        "never",
        "-o",
        str(output_file),
        prompt,
    ]
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=settings.codex_exec_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout, stderr = process.communicate()
        details = "\n".join(part.strip() for part in [stdout or "", stderr or ""] if part and part.strip()).strip()
        if details:
            if len(details) > 4000:
                details = details[:4000] + "\n...[truncated]"
            raise CodexSessionError(f"Codex assistant run timed out.\n{details}") from exc
        raise CodexSessionError("Codex assistant run timed out.") from exc
    stdout = stdout or ""
    stderr = stderr or ""

    if process.returncode != 0:
        raise CodexSessionError(stderr.strip() or stdout.strip() or "Codex assistant run failed.")
    mcp_failure = _detect_mcp_startup_failure(stdout=stdout, stderr=stderr)
    if mcp_failure is not None:
        raise CodexSessionError(mcp_failure)

    assistant_message = output_file.read_text(encoding="utf-8").strip() if output_file.exists() else ""
    result = {
        "assistant_mode": "codex_mcp_stdio_global",
        "assistant_message": assistant_message,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
        "log_file": str(output_file),
        "session_root": str(paths.session_root),
        "mcp_transport": "stdio",
        "mcp_server_name": _mcp_server_name(settings, session_id),
        "mcp_server_command": str(_stdio_mcp_script_path(settings)),
        "active_session_pointer": str(active_codex_session_pointer_path(settings)),
    }
    state.refresh_from_session_file(session_id)
    state.record_assistant_run(result)
    return result


def cleanup_codex_session(
    *,
    settings: Settings,
    state: SellerClientState,
    session_id: str,
) -> None:
    clear_active_codex_session_pointer(settings, session_id=session_id)
    state.cleanup_session(session_id)


def _register_mcp_server(settings: Settings, paths: SessionRuntimePaths) -> None:
    del paths
    _attach_stdio_mcp_to_global_config(settings)


def _mcp_server_name(settings: Settings, session_id: str) -> str:
    del session_id
    return settings.codex_mcp_server_name_prefix


def _codex_env(settings: Settings, paths: SessionRuntimePaths) -> dict[str, str]:
    env = os.environ.copy()
    env["SELLER_CLIENT_SESSION_FILE"] = str(paths.session_file)
    env["SELLER_CLIENT_ACTIVE_SESSION_POINTER"] = str(active_codex_session_pointer_path(settings))
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    return env


def _attach_stdio_mcp_to_global_config(settings: Settings) -> None:
    config_path = _global_codex_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    updated = _upsert_mcp_block(existing, _mcp_server_name(settings, ""), _desired_stdio_mcp_block(settings))
    if updated != existing:
        config_path.write_text(updated, encoding="utf-8")


def _desired_stdio_mcp_block(settings: Settings) -> str:
    python_exe = _normalized_path(shutil.which("python") or sys.executable)
    script_path = _normalized_path(str(_stdio_mcp_script_path(settings)))
    cwd_path = _normalized_path(str(settings.project_root))
    return (
        f"\n[mcp_servers.{_mcp_server_name(settings, '')}]\n"
        f"command = {json.dumps(python_exe, ensure_ascii=False)}\n"
        f"args = [{json.dumps(script_path, ensure_ascii=False)}]\n"
        f"cwd = {json.dumps(cwd_path, ensure_ascii=False)}\n"
    )


def _upsert_mcp_block(config_text: str, server_name: str, block: str) -> str:
    pattern = re.compile(rf"(?ms)^\[mcp_servers\.{re.escape(server_name)}\]\n.*?(?=^\[|\Z)")
    stripped = config_text.rstrip()
    if pattern.search(stripped):
        updated = pattern.sub(block.strip() + "\n\n", stripped, count=1)
        return updated.rstrip() + "\n"
    if not stripped:
        return block.lstrip()
    return stripped + block + "\n"


def _normalized_path(value: str) -> str:
    return value.replace("\\", "/")


def _stdio_mcp_script_path(settings: Settings) -> Path:
    return settings.project_root / "scripts" / "run-seller-fastmcp.py"


def _remove_stale_global_mcp_server(settings: Settings, server_name: str, *, env: dict[str, str]) -> None:
    details = _mcp_get_output(settings, server_name, env=env)
    if not details:
        return
    session_file = _extract_session_file_path(details)
    if session_file is None or session_file.exists():
        return
    subprocess.run(
        _codex_command(settings) + ["mcp", "remove", server_name],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    _remove_mcp_sections_from_global_config(server_name)


def _mcp_get_output(settings: Settings, server_name: str, *, env: dict[str, str]) -> str:
    completed = subprocess.run(
        _codex_command(settings) + ["mcp", "get", server_name],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if completed.returncode != 0:
        return ""
    return f"{completed.stdout or ''}\n{completed.stderr or ''}".strip()


def _extract_session_file_path(details: str) -> Path | None:
    marker = "--session-file "
    if marker not in details:
        return None
    tail = details.split(marker, 1)[1].strip()
    line = tail.splitlines()[0].strip()
    if not line:
        return None
    return Path(line)


def _remove_mcp_sections_from_global_config(server_name: str) -> None:
    config_path = _global_codex_config_path()
    if not config_path.exists():
        return
    text = config_path.read_text(encoding="utf-8")
    target_sections = {
        f"mcp_servers.{server_name}",
        f"mcp_servers.{server_name}.env",
    }
    lines = text.splitlines()
    output: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1]
            skip = section_name in target_sections
            if skip:
                continue
        if skip:
            continue
        output.append(line)
    updated = "\n".join(output).rstrip() + "\n"
    if updated != text:
        config_path.write_text(updated, encoding="utf-8")


def _prune_prefixed_mcp_sections_from_global_config(prefix: str, *, keep_name: str) -> None:
    config_path = _global_codex_config_path()
    if not config_path.exists():
        return
    text = config_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    output: list[str] = []
    skip = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1]
            parts = section_name.split(".")
            skip = False
            if len(parts) >= 2 and parts[0] == "mcp_servers":
                server_name = parts[1]
                if server_name.startswith(f"{prefix}-") and server_name != keep_name:
                    skip = True
            if skip:
                continue
        if skip:
            continue
        output.append(line)

    updated = "\n".join(output).rstrip() + "\n"
    if updated != text:
        config_path.write_text(updated, encoding="utf-8")


def _global_codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def _codex_command(settings: Settings) -> list[str]:
    candidate = shutil.which(settings.codex_command)
    if candidate is None:
        raise CodexSessionError(f"Unable to locate Codex CLI command: {settings.codex_command}")
    return [candidate]


def _build_assistant_prompt(snapshot: dict[str, Any], user_message: str) -> str:
    prompt_state = _build_prompt_state_summary(snapshot)
    prompt_state_json = json.dumps(prompt_state, ensure_ascii=False, indent=2)
    if len(prompt_state_json) > _PROMPT_MAX_STATE_JSON_CHARS:
        prompt_state_json = (
            prompt_state_json[: _PROMPT_MAX_STATE_JSON_CHARS].rstrip()
            + "\n...[truncated for Windows command-line safety]"
        )
    request_directive = _request_execution_directive(user_message)
    return (
        "You are the seller onboarding assistant for Pivot Network.\n"
        "Use only the configured MCP tools for this session.\n"
        "Do not assume shell access and do not ask the user to edit files manually.\n"
        "If the user request is already operationally specific, you must complete it in this run instead of asking what to do next.\n"
        "Work from the existing backend onboarding contract, the generated phase-1 drafts, and the local environment health tools.\n"
        "Prefer the controlled workflow tools for environment checks, overlay checks, join workflow, and diagnostics export.\n"
        "The MCP tools are the supported surface for operating local script-backed workflows; use them instead of asking for raw shell access.\n"
        "If you need to discover or confirm the supported local script-backed execution surface, call list_script_capabilities first.\n"
        "When the user asks for onboarding state, health checks, overlay checks, join workflow, refresh, or TCP validation, you must call the relevant MCP tools before replying.\n"
        "Do not reply with a generic capabilities summary when tool calls are applicable.\n"
        "When the user asks to clear, reset, clean up, or retry seller join state from scratch, call cleanup_join_state before retrying the join flow.\n"
        "For stable join execution, prefer this order unless the user explicitly narrows it: list_script_capabilities, refresh_onboarding_session, read_join_material, prepare_machine_wireguard, execute_guided_join.\n"
        "For seller join or verification requests, call execute_guided_join first unless the user explicitly asks for a narrower tool.\n"
        "Treat short requests like 'help me join', 'join swarm', '帮我接入', or '帮我加入 swarm' as a full seller join request unless the user narrows the scope.\n"
        "If prepare_machine_wireguard reports missing_machine_wireguard_config, state that exact prerequisite instead of pretending the machine can join.\n"
        "Your join-effect answer must explicitly cover: machine WireGuard config preparation, local environment health, join material, local join result, manager raw truth, manager task execution, backend authoritative target, and minimum TCP validation.\n"
        "Treat machine WireGuard config, local join state, manager raw truth, manager task execution, backend authoritative target, and TCP validation as separate layers.\n"
        "The completion standard for seller join verification is manager-side task execution on the selected worker, not only local swarm active state.\n"
        "If a required runtime fact is missing, state the exact missing field instead of guessing.\n"
        f"{request_directive}"
        "Current local state:\n"
        f"{prompt_state_json}\n\n"
        "User request:\n"
        f"{user_message}\n"
    )


def _request_execution_directive(user_message: str) -> str:
    if not _is_join_or_verification_request(user_message):
        return ""
    return (
        "This specific user request is a seller join / verification request and is already sufficiently specified.\n"
        "Do not answer with a capabilities overview.\n"
        "Do not ask the user what they want to do next.\n"
        "In this run, call MCP tools before replying.\n"
        "Use this order unless a tool proves a later step is unnecessary: list_script_capabilities, refresh_onboarding_session, read_join_material, prepare_machine_wireguard, execute_guided_join.\n"
        "If execute_guided_join does not already prove manager-side task execution, call verify_manager_task before replying.\n"
        "If the machine is already joined correctly, still run the verification path and explain that the result is already healthy.\n"
        "Your final answer for this request must say whether manager-side task execution is verified right now.\n"
    )


def _is_join_or_verification_request(user_message: str) -> bool:
    lowered = (user_message or "").lower()
    return any(
        token in lowered
        for token in (
            "join",
            "join workflow",
            "swarm",
            "加入",
            "接入",
            "入网",
            "manager task",
            "manager 那边",
            "验证",
            "核验",
        )
    )


def _build_prompt_state_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    onboarding = snapshot.get("onboarding_session")
    runtime_evidence = snapshot.get("runtime_evidence")
    return _compact_dict(
        {
            "current_user": _pick_fields(snapshot.get("current_user"), ("id", "email")),
            "auth_session": _pick_fields(snapshot.get("auth_session"), ("expires_at",)),
            "window_session": _pick_fields(
                snapshot.get("window_session"),
                ("session_id", "status", "opened_at", "last_heartbeat_at", "ttl_seconds"),
            ),
            "onboarding_session": _build_onboarding_summary(onboarding if isinstance(onboarding, dict) else None),
            "runtime_evidence": _build_runtime_evidence_summary(
                runtime_evidence if isinstance(runtime_evidence, dict) else None
            ),
            "local_health_snapshot": _build_local_health_summary(
                snapshot.get("local_health_snapshot")
                if isinstance(snapshot.get("local_health_snapshot"), dict)
                else None
            ),
            "last_runtime_workflow": _build_runtime_workflow_summary(
                snapshot.get("last_runtime_workflow")
                if isinstance(snapshot.get("last_runtime_workflow"), dict)
                else None
            ),
            "paths": _pick_fields(snapshot.get("paths"), ("session_root", "session_file", "logs_dir", "workspace_dir")),
        }
    )


def _build_onboarding_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return _compact_dict(
        {
            "session_id": _summary_scalar(payload.get("session_id")),
            "seller_user_id": _summary_scalar(payload.get("seller_user_id")),
            "status": _summary_scalar(payload.get("status")),
            "requested_offer_tier": _summary_scalar(payload.get("requested_offer_tier")),
            "requested_accelerator": _summary_scalar(payload.get("requested_accelerator")),
            "requested_compute_node_id": _summary_scalar(payload.get("requested_compute_node_id")),
            "expected_wireguard_ip": _summary_scalar(payload.get("expected_wireguard_ip")),
            "effective_target_addr": _summary_scalar(payload.get("effective_target_addr")),
            "effective_target_source": _summary_scalar(payload.get("effective_target_source")),
            "truth_authority": _summary_scalar(payload.get("truth_authority")),
            "swarm_join_material": _compact_dict(
                {
                    "manager_addr": _summary_scalar((payload.get("swarm_join_material") or {}).get("manager_addr")),
                    "manager_port": _summary_scalar((payload.get("swarm_join_material") or {}).get("manager_port")),
                    "recommended_compute_node_id": _summary_scalar(
                        (payload.get("swarm_join_material") or {}).get("recommended_compute_node_id")
                    ),
                    "registry_host": _summary_scalar((payload.get("swarm_join_material") or {}).get("registry_host")),
                    "registry_port": _summary_scalar((payload.get("swarm_join_material") or {}).get("registry_port")),
                    "recommended_labels": _summary_mapping(
                        (payload.get("swarm_join_material") or {}).get("recommended_labels")
                    ),
                }
            ),
            "required_labels": _summary_mapping(payload.get("required_labels")),
            "manager_acceptance": _pick_fields(
                payload.get("manager_acceptance"),
                (
                    "status",
                    "matched",
                    "detail",
                    "expected_wireguard_ip",
                    "observed_manager_node_addr",
                    "node_ref",
                    "checked_at",
                ),
            ),
            "minimum_tcp_validation": _pick_fields(
                payload.get("minimum_tcp_validation"),
                ("reachable", "target_host", "target_port", "validated_at", "error"),
            ),
            "last_join_complete": _build_last_join_complete_summary(
                payload.get("last_join_complete") if isinstance(payload.get("last_join_complete"), dict) else None
            ),
        }
    )


def _build_last_join_complete_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return _compact_dict(
        {
            "compute_node_id": _summary_scalar(payload.get("compute_node_id")),
            "join_mode": _summary_scalar(payload.get("join_mode")),
            "path_outcome": _summary_scalar(payload.get("path_outcome")),
            "success_standard": _summary_scalar(payload.get("success_standard")),
            "completed_at": _summary_scalar(payload.get("completed_at") or payload.get("recorded_at")),
            "step_names": _extract_step_names(payload.get("steps")),
            "join_effect": _build_join_effect_summary(
                payload.get("join_effect") if isinstance(payload.get("join_effect"), dict) else None
            ),
            "manager_task_execution": _build_manager_task_summary(
                payload.get("manager_task_execution")
                if isinstance(payload.get("manager_task_execution"), dict)
                else None
            ),
        }
    )


def _build_runtime_evidence_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return _compact_dict(
        {
            "updated_at": _summary_scalar(payload.get("updated_at")),
            "latest_correction": _pick_fields(
                payload.get("latest_correction"),
                (
                    "correction_kind",
                    "outcome",
                    "reported_phase",
                    "join_mode",
                    "target_host",
                    "target_port",
                    "observed_wireguard_ip",
                    "recorded_at",
                ),
            ),
            "latest_tcp_validation": _pick_fields(
                payload.get("latest_tcp_validation"),
                ("validation_kind", "target_label", "host", "port", "reachable", "validated_at", "error"),
            ),
        }
    )


def _build_local_health_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    docker = payload.get("docker") if isinstance(payload.get("docker"), dict) else {}
    wireguard = payload.get("wireguard") if isinstance(payload.get("wireguard"), dict) else {}
    return _compact_dict(
        {
            "captured_at": _summary_scalar(payload.get("captured_at") or payload.get("checked_at")),
            "docker": _compact_dict(
                {
                    "daemon_accessible": _summary_scalar(docker.get("daemon_accessible")),
                    "local_node_state": _summary_scalar(docker.get("local_node_state")),
                    "node_addr": _summary_scalar(docker.get("node_addr")),
                    "remote_managers": _summary_remote_managers(docker.get("swarm")),
                }
            ),
            "wireguard": _compact_dict(
                {
                    "expected_wireguard_ip": _summary_scalar(wireguard.get("expected_wireguard_ip")),
                    "observed_wireguard_ip": _summary_scalar(wireguard.get("observed_wireguard_ip")),
                    "manager_port_checks": _summary_list_of_fields(
                        wireguard.get("manager_port_checks"),
                        ("port", "reachable", "status", "error"),
                    ),
                    "route_summary": _summary_string_list(wireguard.get("route_summary")),
                }
            ),
        }
    )


def _summary_remote_managers(swarm_payload: Any) -> list[str] | None:
    if not isinstance(swarm_payload, dict):
        return None
    remote_managers = swarm_payload.get("RemoteManagers")
    if not isinstance(remote_managers, list):
        return None
    values: list[str] = []
    for item in remote_managers[:_PROMPT_MAX_LIST_ITEMS]:
        if isinstance(item, dict):
            addr = _summary_scalar(item.get("Addr"))
            if isinstance(addr, str) and addr:
                values.append(addr)
    if len(remote_managers) > _PROMPT_MAX_LIST_ITEMS:
        values.append(f"... (+{len(remote_managers) - _PROMPT_MAX_LIST_ITEMS} more)")
    return values or None


def _build_runtime_workflow_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    payload_section = payload.get("payload") if isinstance(payload.get("payload"), dict) else None
    result_section = payload.get("result") if isinstance(payload.get("result"), dict) else None
    return _compact_dict(
        {
            "kind": _summary_scalar(payload.get("kind")),
            "step": _summary_scalar(payload.get("step")),
            "status": _summary_scalar(payload.get("status")),
            "ok": _summary_scalar(payload.get("ok")),
            "recorded_at": _summary_scalar(payload.get("recorded_at")),
            "completion_standard": _summary_scalar(payload.get("completion_standard")),
            "join_effect": _build_join_effect_summary(
                payload.get("join_effect")
                if isinstance(payload.get("join_effect"), dict)
                else result_section.get("join_effect")
                if isinstance(result_section, dict)
                else None
            ),
            "manager_task_execution": _build_manager_task_summary(
                payload.get("manager_task_execution")
                if isinstance(payload.get("manager_task_execution"), dict)
                else result_section.get("manager_task_execution")
                if isinstance(result_section, dict)
                else payload_section
            ),
        }
    )


def _build_join_effect_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return _compact_dict(
        {
            "success_standard": _summary_scalar(payload.get("success_standard")),
            "path_outcome": _summary_scalar(payload.get("path_outcome")),
            "effective_target_source": _summary_scalar(payload.get("effective_target_source")),
            "swarm_connectivity": _pick_fields(
                payload.get("swarm_connectivity"),
                ("verified", "local_node_state", "local_node_addr", "expected_remote_manager"),
            ),
            "manager_task_execution": _build_manager_task_summary(
                payload.get("manager_task_execution")
                if isinstance(payload.get("manager_task_execution"), dict)
                else None
            ),
            "backend_authoritative_target": _pick_fields(
                payload.get("backend_authoritative_target"),
                ("session_status", "manager_addr", "manager_port", "effective_target_source"),
            ),
            "minimum_tcp_validation": _pick_fields(
                payload.get("minimum_tcp_validation"),
                ("reachable", "target_host", "target_port", "error"),
            ),
            "local_join": _pick_fields(payload.get("local_join"), ("local_node_state", "local_node_addr", "node_id")),
        }
    )


def _build_manager_task_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    nested_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    return _compact_dict(
        {
            "verified": _summary_scalar(payload.get("verified") if "verified" in payload else payload.get("ok")),
            "proof_source": _summary_scalar(payload.get("proof_source") or nested_payload.get("proof_source")),
            "service_name": _summary_scalar(payload.get("service_name") or nested_payload.get("service_name")),
            "task_name": _summary_scalar(payload.get("task_name") or nested_payload.get("task_name")),
            "node_id": _summary_scalar(payload.get("node_id") or nested_payload.get("node_id")),
            "node_addr": _summary_scalar(payload.get("node_addr") or nested_payload.get("node_addr")),
            "message": _summary_scalar(payload.get("message") or nested_payload.get("message")),
        }
    )


def _extract_step_names(payload: Any) -> list[str] | None:
    if not isinstance(payload, list):
        return None
    names: list[str] = []
    for item in payload[:_PROMPT_MAX_LIST_ITEMS]:
        if isinstance(item, dict):
            step_name = _summary_scalar(item.get("step"))
            if isinstance(step_name, str) and step_name:
                names.append(step_name)
    if len(payload) > _PROMPT_MAX_LIST_ITEMS:
        names.append(f"... (+{len(payload) - _PROMPT_MAX_LIST_ITEMS} more)")
    return names or None


def _summary_list_of_fields(payload: Any, fields: tuple[str, ...]) -> list[dict[str, Any]] | None:
    if not isinstance(payload, list):
        return None
    values: list[dict[str, Any]] = []
    for item in payload[:_PROMPT_MAX_LIST_ITEMS]:
        picked = _pick_fields(item, fields)
        if picked:
            values.append(picked)
    if len(payload) > _PROMPT_MAX_LIST_ITEMS:
        values.append({"truncated_count": len(payload) - _PROMPT_MAX_LIST_ITEMS})
    return values or None


def _summary_string_list(payload: Any) -> list[str] | None:
    if not isinstance(payload, list):
        return None
    values: list[str] = []
    for item in payload[:_PROMPT_MAX_LIST_ITEMS]:
        summarized = _summary_scalar(item)
        if isinstance(summarized, str) and summarized:
            values.append(summarized)
    if len(payload) > _PROMPT_MAX_LIST_ITEMS:
        values.append(f"... (+{len(payload) - _PROMPT_MAX_LIST_ITEMS} more)")
    return values or None


def _summary_mapping(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return _compact_dict({str(key): _summary_scalar(value) for key, value in payload.items()})


def _pick_fields(payload: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return _compact_dict({field: _summary_scalar(payload.get(field)) for field in fields})


def _summary_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if len(value) <= _PROMPT_MAX_STRING_CHARS:
            return value
        return value[: _PROMPT_MAX_STRING_CHARS - 16].rstrip() + "... [truncated]"
    return _summary_scalar(str(value))


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _detect_mcp_startup_failure(*, stdout: str, stderr: str) -> str | None:
    combined = "\n".join(part for part in [stderr.strip(), stdout.strip()] if part).strip()
    lowered = combined.lower()
    markers = (
        "mcp startup: failed",
        "failed to start: mcp startup failed",
        "handshaking with mcp server failed",
    )
    if not any(marker in lowered for marker in markers):
        return None

    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    relevant = [line for line in lines if "mcp" in line.lower() or "rmcp" in line.lower()]
    excerpt = "\n".join(relevant[:12]).strip()
    if excerpt:
        return f"Codex MCP startup failed.\n{excerpt}"
    return "Codex MCP startup failed."
