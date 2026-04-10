from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from seller_client_app.codex_session import CodexSessionError, run_codex_assistant
from seller_client_app.config import Settings
from seller_client_app.mcp_server import _invoke_tool, _load_session_context
from seller_client_app.state import SellerClientState


@dataclass(frozen=True, slots=True)
class AssistantIntent:
    prefers_codex: bool
    wants_environment_check: bool
    wants_repair: bool
    wants_overlay_check: bool
    wants_join_workflow: bool
    wants_refresh: bool
    wants_tcp_validation: bool
    wants_export_diagnostics: bool
    wants_state_summary: bool

    @property
    def use_local_workflow(self) -> bool:
        return any(
            [
                self.wants_environment_check,
                self.wants_repair,
                self.wants_overlay_check,
                self.wants_join_workflow,
                self.wants_refresh,
                self.wants_tcp_validation,
                self.wants_export_diagnostics,
                self.wants_state_summary,
            ]
        )


def execute_assistant_request(
    *,
    settings: Settings,
    state: SellerClientState,
    session_id: str,
    user_message: str,
) -> dict[str, Any]:
    intent = classify_assistant_intent(user_message)
    try:
        if intent.wants_join_workflow:
            result = _execute_join_request_via_mcp(
                settings=settings,
                state=state,
                session_id=session_id,
                user_message=user_message,
            )
        else:
            result = run_codex_assistant(
                settings=settings,
                state=state,
                session_id=session_id,
                user_message=user_message,
            )
    except (CodexSessionError, RuntimeError, OSError, ValueError) as exc:
        result = _build_local_state_fallback(
            state=state,
            session_id=session_id,
            user_message=user_message,
            codex_error=str(exc),
            requested_runtime_actions=intent.use_local_workflow,
        )
    state.record_assistant_run(result)
    return result


def _execute_join_request_via_mcp(
    *,
    settings: Settings,
    state: SellerClientState,
    session_id: str,
    user_message: str,
) -> dict[str, Any]:
    session_file = state.write_session_runtime_file()
    if session_file is None:
        raise RuntimeError("Onboarding session is not initialized.")
    session_file_str = str(session_file)
    actions_run: list[dict[str, Any]] = []

    def run_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = _load_session_context(session_file_str)
        result = _invoke_tool(name, arguments or {}, payload, session_file_str)
        actions_run.append(
            {
                "action": name,
                "ok": _tool_call_ok(result),
                "summary": _summarize_tool_result(name, result),
            }
        )
        return result

    def record_failed_action(name: str, error: Exception) -> None:
        actions_run.append(
            {
                "action": name,
                "ok": False,
                "summary": str(error),
            }
        )

    capabilities = run_tool("list_script_capabilities")
    refreshed: dict[str, Any] | None = None
    backend_refresh_error: str | None = None
    try:
        refreshed = run_tool("refresh_onboarding_session")
    except Exception as exc:
        backend_refresh_error = str(exc)
        record_failed_action("refresh_onboarding_session", exc)
    join_material = run_tool("read_join_material")
    prepare_machine_wireguard = run_tool("prepare_machine_wireguard")

    guided_join: dict[str, Any] | None = None
    manager_task_verification: dict[str, Any] | None = None
    network_path: dict[str, Any] | None = None
    if _tool_call_ok(prepare_machine_wireguard):
        if refreshed is not None:
            try:
                guided_join = run_tool("execute_guided_join")
            except Exception as exc:
                backend_refresh_error = backend_refresh_error or str(exc)
                record_failed_action("execute_guided_join", exc)
        if guided_join is None:
            network_path = run_tool("inspect_network_path")
        if not _manager_task_execution_verified(guided_join):
            manager_task_verification = run_tool("verify_manager_task")

    state.refresh_from_session_file(session_id)
    snapshot = state.runtime_snapshot()
    manager_task_verified = _manager_task_execution_verified(guided_join) or _manager_task_execution_verified(
        manager_task_verification
    )
    assistant_message = _build_join_execution_message(
        snapshot=snapshot,
        join_material=join_material,
        prepare_machine_wireguard=prepare_machine_wireguard,
        guided_join=guided_join,
        manager_task_verification=manager_task_verification,
        network_path=network_path,
        backend_refresh_error=backend_refresh_error,
        manager_task_verified=manager_task_verified,
    )
    return {
        "assistant_mode": "mcp_orchestrated_join",
        "assistant_message": assistant_message,
        "user_message": user_message,
        "session_id": session_id,
        "actions_run": actions_run,
        "capabilities": capabilities,
        "refresh_onboarding_session": refreshed,
        "join_material": join_material,
        "prepare_machine_wireguard": prepare_machine_wireguard,
        "guided_join": guided_join,
        "network_path": network_path,
        "manager_task_verification": manager_task_verification,
        "manager_task_verified": manager_task_verified,
        "backend_refresh_error": backend_refresh_error,
        "snapshot": snapshot,
    }


def classify_assistant_intent(user_message: str) -> AssistantIntent:
    lowered = (user_message or "").lower()
    explicit_codex_preference = bool(
        _contains_any(
            lowered,
            (
                "codex",
                "code x",
                "mcp",
                "不要走本地受控",
                "原生",
                "tool call",
                "tool-calling",
            ),
        )
    )
    wants_join_workflow = bool(
        _contains_any(
            lowered,
            (
                "join",
                "join workflow",
                "swarm join",
                "加入",
                "接入",
                "入网",
            ),
        )
    )
    wants_repair = bool(
        _contains_any(
            lowered,
            (
                "repair",
                "fix",
                "install",
                "setup",
                "修复",
                "安装",
                "准备环境",
                "半自动",
            ),
        )
    )
    wants_environment_check = bool(
        wants_join_workflow
        or wants_repair
        or _contains_any(
            lowered,
            (
                "environment",
                "health",
                "doctor",
                "diagnostic",
                "check",
                "检查",
                "环境",
                "健康",
                "诊断",
            ),
        )
    )
    wants_overlay_check = bool(
        wants_join_workflow
        or _contains_any(
            lowered,
            (
                "wireguard",
                "docker",
                "swarm",
                "overlay",
                "network",
                "route",
                "wg",
                "网络",
                "路由",
            ),
        )
    )
    wants_refresh = bool(
        wants_join_workflow
        or _contains_any(
            lowered,
            (
                "refresh",
                "reload",
                "sync",
                "refresh session",
                "刷新",
                "同步",
                "重新获取状态",
            ),
        )
    )
    wants_tcp_validation = bool(
        _contains_any(
            lowered,
            (
                "tcp",
                "port",
                "reachable",
                "reachability",
                "connectivity",
                "validation",
                "可达",
                "连通",
                "端口",
                "探测",
                "校验",
            ),
        )
    )
    wants_export_diagnostics = bool(
        _contains_any(
            lowered,
            (
                "export",
                "diagnostics",
                "diagnostic bundle",
                "logs",
                "导出",
                "诊断包",
                "日志",
            ),
        )
    )
    wants_state_summary = bool(
        wants_join_workflow
        or _contains_any(
            lowered,
            (
                "read",
                "state",
                "status",
                "summary",
                "show",
                "读取",
                "状态",
                "总结",
                "汇总",
                "看一下",
            ),
        )
    )
    prefers_codex = bool(
        explicit_codex_preference
        or any(
            [
                wants_environment_check,
                wants_repair,
                wants_overlay_check,
                wants_join_workflow,
                wants_refresh,
                wants_tcp_validation,
                wants_export_diagnostics,
                wants_state_summary,
            ]
        )
    )
    return AssistantIntent(
        prefers_codex=prefers_codex,
        wants_environment_check=wants_environment_check,
        wants_repair=wants_repair,
        wants_overlay_check=wants_overlay_check,
        wants_join_workflow=wants_join_workflow,
        wants_refresh=wants_refresh,
        wants_tcp_validation=wants_tcp_validation,
        wants_export_diagnostics=wants_export_diagnostics,
        wants_state_summary=wants_state_summary,
    )


def _build_local_state_fallback(
    *,
    state: SellerClientState,
    session_id: str,
    user_message: str,
    codex_error: str,
    requested_runtime_actions: bool = False,
) -> dict[str, Any]:
    snapshot = state.runtime_snapshot()
    preface = (
        "Codex MCP is unavailable on this machine right now, so no actual join, repair, or verification action was executed. "
        "Returning a read-only local state summary instead.\n\n"
        if requested_runtime_actions
        else "Codex MCP is unavailable on this machine right now, so this reply falls back to a read-only local state summary.\n\n"
    )
    return {
        "assistant_mode": "local_state_fallback",
        "assistant_message": preface + _build_state_summary_message(snapshot=snapshot),
        "user_message": user_message,
        "actions_run": [{"action": "read_state", "ok": True}],
        "session_id": session_id,
        "codex_error": codex_error,
        "snapshot": snapshot,
    }


def _build_join_execution_message(
    *,
    snapshot: dict[str, Any],
    join_material: dict[str, Any],
    prepare_machine_wireguard: dict[str, Any],
    guided_join: dict[str, Any] | None,
    manager_task_verification: dict[str, Any] | None,
    network_path: dict[str, Any] | None,
    backend_refresh_error: str | None,
    manager_task_verified: bool,
) -> str:
    onboarding = snapshot.get("onboarding_session") or {}
    join_target = _join_target_string(join_material, onboarding)
    prepare_status = prepare_machine_wireguard.get("status") or ("ok" if _tool_call_ok(prepare_machine_wireguard) else "failed")
    if not _tool_call_ok(prepare_machine_wireguard):
        guidance = prepare_machine_wireguard.get("guidance") or prepare_machine_wireguard.get("error") or "unknown"
        lines = [
            "MCP join flow stopped before Docker Swarm join because machine WireGuard config is not ready.",
            f"WireGuard config preparation: {prepare_status}",
            f"Join target: {join_target}",
            f"Backend session status: {onboarding.get('status') or 'unknown'}",
            f"Blocking prerequisite: {guidance}",
        ]
        return "\n".join(lines)

    join_effect = _extract_join_effect(guided_join)
    success_standard = (
        (join_effect.get("success_standard") if isinstance(join_effect, dict) else None) or "manager_task_execution"
    )
    manager_task_summary = _describe_manager_task_result(
        guided_join=guided_join,
        manager_task_verification=manager_task_verification,
    )
    lines = [
        "MCP join flow executed from the natural-language request.",
        f"WireGuard config preparation: {prepare_status}",
        f"Join target: {join_target}",
        f"Backend session status: {onboarding.get('status') or 'unknown'}"
        + (f" (refresh unavailable: {backend_refresh_error})" if backend_refresh_error else ""),
        f"Local join: {_describe_local_join(snapshot)}",
        f"Manager raw truth: {_describe_manager_raw_truth((onboarding.get('manager_acceptance') or {}))}",
        f"Swarm connectivity: {_describe_swarm_connectivity(snapshot, network_path=network_path)}",
        f"Manager task execution: {manager_task_summary}",
        f"Completion standard: {success_standard}",
        "Verdict: manager-side task execution is verified."
        if manager_task_verified
        else "Verdict: manager-side task execution is not verified yet.",
    ]
    return "\n".join(lines)


def _build_state_summary_message(*, snapshot: dict[str, Any]) -> str:
    onboarding = snapshot.get("onboarding_session") or {}
    health_snapshot = snapshot.get("local_health_snapshot") or {}
    health_summary = health_snapshot.get("summary") or {}
    health_status = health_summary.get("status") or "unknown"
    health_warnings = list(health_summary.get("warnings") or [])
    manager_acceptance = onboarding.get("manager_acceptance") or {}
    local_join = _describe_local_join(snapshot)
    manager_raw_truth = _describe_manager_raw_truth(manager_acceptance)
    authoritative_target = _describe_authoritative_target(onboarding)
    swarm_summary = _describe_swarm_connectivity(snapshot)
    tcp_summary = _describe_tcp_validation(onboarding.get("minimum_tcp_validation") or {})

    lines = [
        "Read-only local state summary:",
        f"Session: {onboarding.get('session_id') or 'not_initialized'}",
        f"Backend session status: {onboarding.get('status') or 'unknown'}",
        f"Local environment: {health_status}" + (f" (warnings: {', '.join(health_warnings)})" if health_warnings else ""),
        f"Local join: {local_join}",
        f"Manager raw truth: {manager_raw_truth}",
        f"Backend authoritative target: {authoritative_target}",
        f"Swarm connectivity: {swarm_summary}",
        f"Minimum TCP validation: {tcp_summary}",
    ]
    return "\n".join(lines)


def _join_target_string(join_material: dict[str, Any], onboarding: dict[str, Any]) -> str:
    manager_addr = join_material.get("manager_addr") or ((onboarding.get("swarm_join_material") or {}).get("manager_addr"))
    manager_port = join_material.get("manager_port") or ((onboarding.get("swarm_join_material") or {}).get("manager_port"))
    if manager_addr and manager_port:
        return f"{manager_addr}:{manager_port}"
    if manager_addr:
        return str(manager_addr)
    return "unknown"


def _tool_call_ok(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    if "ok" in result:
        return bool(result.get("ok"))
    return True


def _summarize_tool_result(name: str, result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return f"{name}: no result"
    if name == "prepare_machine_wireguard":
        return str(result.get("status") or ("ok" if _tool_call_ok(result) else "failed"))
    if name == "execute_guided_join":
        join_effect = _extract_join_effect(result)
        if isinstance(join_effect, dict):
            return ", ".join(
                [
                    f"success_standard={join_effect.get('success_standard') or 'unknown'}",
                    f"manager_task_verified={_manager_task_execution_verified(result)}",
                ]
            )
    if name == "verify_manager_task":
        return "verified" if _manager_task_execution_verified(result) else "not_verified"
    return "ok" if _tool_call_ok(result) else "failed"


def _extract_join_effect(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    join_effect = result.get("join_effect")
    return join_effect if isinstance(join_effect, dict) else {}


def _manager_task_execution_verified(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    join_effect = _extract_join_effect(result)
    manager_task = join_effect.get("manager_task_execution")
    if isinstance(manager_task, dict) and "verified" in manager_task:
        return bool(manager_task.get("verified"))
    manager_task = result.get("manager_task_execution")
    if isinstance(manager_task, dict):
        if "verified" in manager_task:
            return bool(manager_task.get("verified"))
        payload = manager_task.get("payload")
        if isinstance(payload, dict) and "task_execution_verified" in payload:
            return bool(payload.get("task_execution_verified"))
        if "ok" in manager_task:
            return bool(manager_task.get("ok"))
    payload = result.get("payload")
    if isinstance(payload, dict) and "task_execution_verified" in payload:
        return bool(payload.get("task_execution_verified"))
    if "ok" in result and result.get("step") == "manager_task_execution":
        return bool(result.get("ok"))
    return False


def _describe_manager_task_result(
    *,
    guided_join: dict[str, Any] | None,
    manager_task_verification: dict[str, Any] | None,
) -> str:
    for candidate in [guided_join, manager_task_verification]:
        if not isinstance(candidate, dict):
            continue
        join_effect = _extract_join_effect(candidate)
        manager_task = join_effect.get("manager_task_execution") if isinstance(join_effect, dict) else None
        if not isinstance(manager_task, dict):
            manager_task = candidate.get("manager_task_execution")
        if not isinstance(manager_task, dict):
            payload = candidate.get("payload")
            manager_task = payload if isinstance(payload, dict) else None
        if not isinstance(manager_task, dict):
            continue
        verified = manager_task.get("verified")
        if verified is None and isinstance(manager_task.get("payload"), dict):
            verified = manager_task["payload"].get("task_execution_verified")
        proof_source = manager_task.get("proof_source")
        if proof_source is None and isinstance(manager_task.get("payload"), dict):
            proof_source = manager_task["payload"].get("proof_source")
        service_name = manager_task.get("service_name")
        if service_name is None and isinstance(manager_task.get("payload"), dict):
            service_name = manager_task["payload"].get("service_name")
        parts = [
            f"verified={verified}",
            None if proof_source is None else f"proof_source={proof_source}",
            None if service_name is None else f"service={service_name}",
        ]
        return ", ".join(part for part in parts if part)
    return "not_verified"


def _describe_local_join(snapshot: dict[str, Any]) -> str:
    health_snapshot = snapshot.get("local_health_snapshot") or {}
    docker = health_snapshot.get("docker") or {}
    node_state = docker.get("local_node_state")
    node_addr = docker.get("node_addr")

    workflow = snapshot.get("last_runtime_workflow") or {}
    workflow_payload = (
        workflow.get("workflow")
        if workflow.get("kind") in {"standard_join_workflow", "execute_join_workflow", "guided_join_assessment", "execute_guided_join"}
        else {}
    )
    join_payload = (workflow_payload or {}).get("payload") or {}
    join_result = join_payload.get("join_result") if isinstance(join_payload, dict) else {}
    after_state = _parse_json_dict((join_result or {}).get("after_state"))
    node_state = after_state.get("LocalNodeState") or node_state
    node_addr = after_state.get("NodeAddr") or node_addr

    onboarding = snapshot.get("onboarding_session") or {}
    if node_state or node_addr:
        details = ", ".join(
            item
            for item in [
                None if node_state is None else f"LocalNodeState={node_state}",
                None if node_addr is None else f"NodeAddr={node_addr}",
            ]
            if item
        )
        return details
    if onboarding.get("last_join_complete"):
        return "join_complete 已提交，但本地 Docker 状态摘要缺失"
    return "未确认"


def _describe_manager_raw_truth(manager_acceptance: dict[str, Any]) -> str:
    if not manager_acceptance:
        return "未返回"
    details = [
        f"status={manager_acceptance.get('status') or 'unknown'}",
        f"matched={manager_acceptance.get('matched')}",
        f"observed_addr={manager_acceptance.get('observed_manager_node_addr') or 'unknown'}",
        f"detail={manager_acceptance.get('detail') or 'unknown'}",
    ]
    return ", ".join(details)


def _describe_authoritative_target(onboarding: dict[str, Any]) -> str:
    target = onboarding.get("effective_target_addr")
    source = onboarding.get("effective_target_source") or onboarding.get("truth_authority")
    if target:
        return f"{target} (source={source or 'unknown'})"
    return f"未建立 (truth_authority={source or 'unknown'})"


def _describe_tcp_validation(tcp_validation: dict[str, Any]) -> str:
    if not tcp_validation:
        return "未记录"
    host = tcp_validation.get("target_addr") or tcp_validation.get("host") or "unknown"
    port = tcp_validation.get("target_port") or tcp_validation.get("port") or "unknown"
    reachable = tcp_validation.get("reachable")
    return f"reachable={reachable}, target={host}:{port}"

def _describe_swarm_connectivity(snapshot: dict[str, Any], network_path: dict[str, Any] | None = None) -> str:
    if isinstance(network_path, dict):
        swarm_connectivity = network_path.get("swarm_connectivity")
        if isinstance(swarm_connectivity, dict):
            return ", ".join(
                [
                    f"standard={network_path.get('success_standard') or 'docker_swarm_connectivity'}",
                    f"verified={swarm_connectivity.get('verified')}",
                    f"local_state={swarm_connectivity.get('local_node_state') or 'unknown'}",
                    f"local_addr={swarm_connectivity.get('local_node_addr') or 'unknown'}",
                    f"expected_manager={swarm_connectivity.get('expected_remote_manager') or 'unknown'}",
                ]
            )
    workflow = snapshot.get("last_runtime_workflow") or {}
    workflow_payload = (
        workflow.get("workflow")
        if workflow.get("kind") in {"standard_join_workflow", "execute_join_workflow", "guided_join_assessment", "execute_guided_join"}
        else {}
    )
    summary = ((workflow_payload or {}).get("payload") or {}).get("summary") or {}
    if summary:
        return ", ".join(
            [
                f"standard={summary.get('success_standard') or 'docker_swarm_connectivity'}",
                f"verified={summary.get('swarm_connectivity_verified')}",
                f"local_active={summary.get('local_swarm_active')}",
                f"manager_matched={summary.get('manager_acceptance_matched')}",
                f"path_outcome={summary.get('path_outcome') or 'unknown'}",
            ]
        )

    manager_acceptance = (snapshot.get("onboarding_session") or {}).get("manager_acceptance") or {}
    if manager_acceptance:
        return ", ".join(
            [
                "standard=docker_swarm_connectivity",
                f"manager_status={manager_acceptance.get('status') or 'unknown'}",
                f"manager_matched={manager_acceptance.get('matched')}",
            ]
        )
    return "standard=docker_swarm_connectivity, not_yet_verified"


def _parse_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _contains_any(text: str, candidates: tuple[str, ...]) -> bool:
    return any(candidate in text for candidate in candidates)
