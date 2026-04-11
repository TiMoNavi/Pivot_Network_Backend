from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from buyer_client_app.config import Settings
from buyer_client_app.mcp_server import _invoke_tool
from buyer_client_app.state import BuyerClientState

_GRANT_CODE_RE = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{24,})(?![A-Za-z0-9_-])")
_GRANT_ID_RE = re.compile(r"\bgrant_[A-Za-z0-9]+\b")
_SESSION_ID_RE = re.compile(r"\bruntime_session_[A-Za-z0-9]+\b")
_ABS_PATH_RE = re.compile(r"(?P<path>(?:~|/|[A-Za-z]:[\\/])[^\s'\"`]+)")
_BACKTICK_COMMAND_RE = re.compile(r"`([^`]+)`")


@dataclass(frozen=True, slots=True)
class AssistantIntent:
    wants_grant_selection: bool
    wants_session_create: bool
    wants_session_refresh: bool
    wants_wireguard_up: bool
    wants_shell_open: bool
    wants_workspace_sync: bool
    wants_task_submit: bool
    wants_result_readback: bool
    wants_state_summary: bool

    @property
    def wants_end_to_end(self) -> bool:
        return any(
            [
                self.wants_session_create,
                self.wants_session_refresh,
                self.wants_wireguard_up,
                self.wants_shell_open,
                self.wants_workspace_sync,
                self.wants_task_submit,
                self.wants_result_readback,
            ]
        )


def execute_assistant_request(
    *,
    settings: Settings,
    state: BuyerClientState,
    user_message: str,
) -> dict[str, Any]:
    del settings
    intent = classify_assistant_intent(user_message)
    actions_run: list[dict[str, Any]] = []
    extracted_grant_code = extract_grant_code(user_message)
    extracted_grant_id = extract_grant_id(user_message)
    extracted_runtime_session_id = extract_runtime_session_id(user_message)
    extracted_workspace_path = extract_workspace_path(user_message)
    extracted_command = extract_command(user_message)
    if extracted_workspace_path and not state.current_workspace_selection():
        state.set_workspace_selection({"path": extracted_workspace_path, "source": "assistant_message"})
    snapshot_before = _safe_read_runtime_state(state)
    selected_grant: dict[str, Any] | None = None
    task_result: dict[str, Any] | None = None
    task_logs: dict[str, Any] | None = None
    shell_result: dict[str, Any] | None = None
    workspace_result: dict[str, Any] | None = None

    try:
        if extracted_grant_code:
            _run_tool(
                state=state,
                actions_run=actions_run,
                name="import_grant_code",
                arguments={"grant_code": extracted_grant_code},
            )

        if _needs_active_grant_refresh(state, intent, extracted_grant_id, extracted_grant_code):
            grants_payload = _run_tool(state=state, actions_run=actions_run, name="list_active_grants")
            selected_grant = _select_grant(grants_payload, state, extracted_grant_id)
        else:
            selected_grant = _select_grant(None, state, extracted_grant_id)

        if _needs_runtime_session(state, intent, extracted_command, extracted_workspace_path):
            if state.current_runtime_session() is None or extracted_grant_code or extracted_grant_id or intent.wants_session_create:
                create_arguments: dict[str, Any] = {"network_mode": "wireguard"}
                if extracted_grant_code:
                    create_arguments["grant_code"] = extracted_grant_code
                elif extracted_grant_id:
                    create_arguments["grant_id"] = extracted_grant_id
                elif selected_grant is not None:
                    create_arguments["grant_id"] = selected_grant["id"]
                _run_tool(
                    state=state,
                    actions_run=actions_run,
                    name="create_runtime_session",
                    arguments=create_arguments,
                )
            elif intent.wants_session_refresh or state.current_runtime_session() is not None:
                refresh_arguments: dict[str, Any] = {}
                if extracted_runtime_session_id:
                    refresh_arguments["runtime_session_id"] = extracted_runtime_session_id
                _run_tool(
                    state=state,
                    actions_run=actions_run,
                    name="refresh_runtime_session",
                    arguments=refresh_arguments,
                )
        elif intent.wants_session_refresh and (state.current_runtime_session() or extracted_runtime_session_id):
            refresh_arguments = {}
            if extracted_runtime_session_id:
                refresh_arguments["runtime_session_id"] = extracted_runtime_session_id
            _run_tool(state=state, actions_run=actions_run, name="refresh_runtime_session", arguments=refresh_arguments)

        if _needs_wireguard(state, intent, extracted_command, extracted_workspace_path):
            wireguard_state = state.current_wireguard_state() or {}
            if str(wireguard_state.get("status") or "").lower() != "up":
                _run_tool(state=state, actions_run=actions_run, name="wireguard_up")

        if _needs_shell(intent, extracted_command, extracted_workspace_path):
            shell_result = _run_tool(state=state, actions_run=actions_run, name="open_shell")

        workspace_path = extracted_workspace_path or ((state.current_workspace_selection() or {}).get("path"))
        if workspace_path and _needs_workspace_sync(intent, extracted_command, extracted_workspace_path):
            workspace_result = _run_tool(
                state=state,
                actions_run=actions_run,
                name="sync_workspace",
                arguments={"path": workspace_path},
            )

        if extracted_command:
            task_result = _run_tool(
                state=state,
                actions_run=actions_run,
                name="submit_task_execution",
                arguments={"command": extracted_command},
            )
            task_logs = _run_tool(
                state=state,
                actions_run=actions_run,
                name="tail_task_logs",
                arguments={"task_id": task_result.get("id")},
            )
        elif intent.wants_result_readback:
            latest_task_id = _latest_task_id(state)
            if latest_task_id:
                task_logs = _run_tool(
                    state=state,
                    actions_run=actions_run,
                    name="tail_task_logs",
                    arguments={"task_id": latest_task_id},
                )
    except Exception as exc:  # noqa: BLE001
        snapshot_after = _safe_read_runtime_state(state)
        result = {
            "assistant_mode": "mcp_nl_orchestrated",
            "ok": False,
            "user_message": user_message,
            "assistant_message": _build_failure_message(
                user_message=user_message,
                actions_run=actions_run,
                error=str(exc),
                snapshot_after=snapshot_after,
            ),
            "actions_run": actions_run,
            "error": str(exc),
            "snapshot_before": snapshot_before,
            "snapshot_after": snapshot_after,
        }
        state.record_assistant_run(result)
        return result

    snapshot_after = _safe_read_runtime_state(state)
    result = {
        "assistant_mode": "mcp_nl_orchestrated",
        "ok": True,
        "user_message": user_message,
        "assistant_message": _build_success_message(
            user_message=user_message,
            actions_run=actions_run,
            selected_grant=selected_grant,
            shell_result=shell_result,
            workspace_result=workspace_result,
            task_result=task_result,
            task_logs=task_logs,
            snapshot_after=snapshot_after,
        ),
        "actions_run": actions_run,
        "selected_grant": selected_grant,
        "shell": shell_result,
        "workspace": workspace_result,
        "task_result": task_result,
        "task_logs": task_logs,
        "snapshot_before": snapshot_before,
        "snapshot_after": snapshot_after,
    }
    state.record_assistant_run(result)
    return result


def classify_assistant_intent(user_message: str) -> AssistantIntent:
    lowered = str(user_message or "").lower()
    wants_grant_selection = _contains_any(
        lowered,
        ("grant", "授权", "凭证", "选择 grant", "导入 grant", "接入码", "access grant"),
    )
    wants_session_create = _contains_any(
        lowered,
        ("create session", "runtime session", "建立会话", "创建会话", "拉起会话", "redeem"),
    )
    wants_session_refresh = _contains_any(
        lowered,
        ("refresh", "刷新", "reload", "更新会话", "重新读取"),
    )
    wants_wireguard_up = _contains_any(
        lowered,
        ("wireguard", "wg", "隧道", "连通", "connect runtime", "连接 runtime"),
    )
    wants_shell_open = _contains_any(
        lowered,
        ("shell", "terminal", "终端", "打开会话", "open shell"),
    )
    wants_workspace_sync = _contains_any(
        lowered,
        ("workspace", "sync", "upload", "工作区", "同步项目", "上传项目", "同步代码"),
    )
    wants_task_submit = bool(extract_command(user_message)) or _contains_any(
        lowered,
        ("run", "execute", "command", "执行", "运行", "task", "任务"),
    )
    wants_result_readback = _contains_any(
        lowered,
        ("result", "log", "stdout", "stderr", "readback", "结果", "日志", "输出"),
    )
    wants_state_summary = not any(
        [
            wants_grant_selection,
            wants_session_create,
            wants_session_refresh,
            wants_wireguard_up,
            wants_shell_open,
            wants_workspace_sync,
            wants_task_submit,
            wants_result_readback,
        ]
    ) or _contains_any(lowered, ("status", "state", "summary", "状态", "概览"))
    return AssistantIntent(
        wants_grant_selection=wants_grant_selection,
        wants_session_create=wants_session_create,
        wants_session_refresh=wants_session_refresh,
        wants_wireguard_up=wants_wireguard_up,
        wants_shell_open=wants_shell_open,
        wants_workspace_sync=wants_workspace_sync,
        wants_task_submit=wants_task_submit,
        wants_result_readback=wants_result_readback,
        wants_state_summary=wants_state_summary,
    )


def extract_grant_code(user_message: str) -> str | None:
    explicit = re.search(r"(?:grant[_ -]?code|access[_ -]?code|授权码|接入码)\s*[:：]?\s*([A-Za-z0-9_-]{24,})", str(user_message or ""), re.IGNORECASE)
    if explicit:
        return explicit.group(1)
    return None


def extract_grant_id(user_message: str) -> str | None:
    match = _GRANT_ID_RE.search(str(user_message or ""))
    return match.group(0) if match else None


def extract_runtime_session_id(user_message: str) -> str | None:
    match = _SESSION_ID_RE.search(str(user_message or ""))
    return match.group(0) if match else None


def extract_workspace_path(user_message: str) -> str | None:
    for match in _ABS_PATH_RE.finditer(str(user_message or "")):
        candidate = match.group("path").rstrip("，。；;,.!?)）]")
        if candidate.startswith("/api/") or candidate.startswith("/local-api/"):
            continue
        return candidate
    return None


def extract_command(user_message: str) -> str | None:
    text = str(user_message or "")
    backtick = _BACKTICK_COMMAND_RE.search(text)
    if backtick:
        command = backtick.group(1).strip()
        return command or None

    patterns = [
        r"(?:执行|运行)\s+(.+?)(?:[。；;]|$)",
        r"(?:run|execute)\s+(.+?)(?:[.;]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            command = match.group(1).strip().strip("`")
            if command:
                return command
    return None


def _needs_active_grant_refresh(
    state: BuyerClientState,
    intent: AssistantIntent,
    extracted_grant_id: str | None,
    extracted_grant_code: str | None,
) -> bool:
    if extracted_grant_code:
        return False
    if extracted_grant_id:
        return True
    if state.current_access_grant() is not None:
        return False
    return intent.wants_grant_selection or intent.wants_end_to_end


def _needs_runtime_session(
    state: BuyerClientState,
    intent: AssistantIntent,
    extracted_command: str | None,
    extracted_workspace_path: str | None,
) -> bool:
    if state.current_runtime_session() is None:
        return True
    return any(
        [
            intent.wants_session_create,
            intent.wants_session_refresh,
            intent.wants_wireguard_up,
            intent.wants_shell_open,
            intent.wants_workspace_sync,
            intent.wants_task_submit,
            intent.wants_result_readback,
            bool(extracted_command),
            bool(extracted_workspace_path),
        ]
    )


def _needs_wireguard(
    state: BuyerClientState,
    intent: AssistantIntent,
    extracted_command: str | None,
    extracted_workspace_path: str | None,
) -> bool:
    if str((state.current_wireguard_state() or {}).get("status") or "").lower() == "up":
        return False
    return any(
        [
            intent.wants_wireguard_up,
            intent.wants_shell_open,
            intent.wants_workspace_sync,
            intent.wants_task_submit,
            intent.wants_result_readback,
            bool(extracted_command),
            bool(extracted_workspace_path),
        ]
    )


def _needs_shell(intent: AssistantIntent, extracted_command: str | None, extracted_workspace_path: str | None) -> bool:
    return any(
        [
            intent.wants_shell_open,
            intent.wants_workspace_sync,
            intent.wants_task_submit,
            intent.wants_result_readback,
            bool(extracted_command),
            bool(extracted_workspace_path),
        ]
    )


def _needs_workspace_sync(intent: AssistantIntent, extracted_command: str | None, extracted_workspace_path: str | None) -> bool:
    return bool(extracted_workspace_path) or intent.wants_workspace_sync or bool(extracted_command)


def _run_tool(
    *,
    state: BuyerClientState,
    actions_run: list[dict[str, Any]],
    name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _invoke_tool(name, arguments or {})
    state.refresh_from_disk()
    actions_run.append(
        {
            "tool": name,
            "arguments": dict(arguments or {}),
            "ok": True,
            "result": result,
        }
    )
    return result


def _safe_read_runtime_state(state: BuyerClientState) -> dict[str, Any]:
    try:
        result = _invoke_tool("read_runtime_state", {})
    except Exception:
        state.refresh_from_disk()
        return state.runtime_snapshot()
    state.refresh_from_disk()
    return result


def _select_grant(
    grants_payload: dict[str, Any] | None,
    state: BuyerClientState,
    extracted_grant_id: str | None,
) -> dict[str, Any] | None:
    current = state.current_access_grant()
    if extracted_grant_id:
        for item in list((grants_payload or {}).get("items") or []) + ([current] if current else []):
            if isinstance(item, dict) and item.get("id") == extracted_grant_id:
                return dict(item)
        return {"id": extracted_grant_id}
    if current is not None:
        return current
    items = list((grants_payload or {}).get("items") or [])
    if items:
        return dict(items[0])
    return None


def _latest_task_id(state: BuyerClientState) -> str | None:
    history = state.task_execution_history()
    if not history:
        return None
    latest = history[-1]
    value = latest.get("id")
    return str(value).strip() if value else None


def _build_success_message(
    *,
    user_message: str,
    actions_run: list[dict[str, Any]],
    selected_grant: dict[str, Any] | None,
    shell_result: dict[str, Any] | None,
    workspace_result: dict[str, Any] | None,
    task_result: dict[str, Any] | None,
    task_logs: dict[str, Any] | None,
    snapshot_after: dict[str, Any],
) -> str:
    lines = [f"已按当前 Buyer_Client + MCP 链路处理你的请求：{user_message.strip()}"]
    if selected_grant is not None:
        lines.append(f"Grant: {selected_grant.get('id') or 'selected'}")
    runtime_session = snapshot_after.get("runtime_session") or {}
    if runtime_session:
        lines.append(
            "RuntimeSession: "
            f"{runtime_session.get('id')} / {runtime_session.get('status')} / {runtime_session.get('runtime_bundle_status')}"
        )
    wireguard_state = snapshot_after.get("wireguard_state") or {}
    if wireguard_state:
        lines.append(f"WireGuard: {wireguard_state.get('status')} ({wireguard_state.get('interface_name') or 'n/a'})")
    if shell_result and shell_result.get("shell_embed_url"):
        lines.append(f"Shell: {shell_result['shell_embed_url']}")
    if workspace_result:
        workspace_selection = workspace_result.get("workspace_selection") or {}
        lines.append(f"Workspace: {workspace_selection.get('path') or 'selected'}")
    if task_result:
        lines.append(
            f"Task: {task_result.get('id')} / exit_code={task_result.get('exit_code')} / status={task_result.get('status')}"
        )
    if task_logs:
        stdout_tail = str(task_logs.get("stdout_tail") or "").strip()
        if stdout_tail:
            lines.append(f"Task stdout tail:\n{stdout_tail}")
    if actions_run:
        lines.append("Actions: " + " -> ".join(action["tool"] for action in actions_run))
    return "\n".join(lines)


def _build_failure_message(
    *,
    user_message: str,
    actions_run: list[dict[str, Any]],
    error: str,
    snapshot_after: dict[str, Any],
) -> str:
    lines = [f"处理该请求时在当前 Buyer_Client + MCP 链路上失败：{user_message.strip()}"]
    if actions_run:
        lines.append("已完成动作: " + " -> ".join(action["tool"] for action in actions_run))
    lines.append(f"Failure: {error}")
    runtime_session = (snapshot_after.get("runtime_session") or {}).get("id")
    if runtime_session:
        lines.append(f"Current runtime session: {runtime_session}")
    return "\n".join(lines)


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)
