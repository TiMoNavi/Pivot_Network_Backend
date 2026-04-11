from __future__ import annotations

import json
import sys
from typing import Any

from buyer_client_app.backend import BackendClient
from buyer_client_app.config import get_settings
from buyer_client_app.session_ops import (
    create_runtime_session,
    import_grant_code,
    open_shell,
    read_workspace_status,
    refresh_active_grants,
    refresh_runtime_session,
    submit_task_execution,
    sync_workspace_selection,
    tail_task_logs,
    wireguard_down,
    wireguard_up,
)
from buyer_client_app.state import BuyerClientState


def _load_state() -> BuyerClientState:
    return BuyerClientState.load_from_disk(get_settings())


def _backend_client(state: BuyerClientState) -> BackendClient:
    token = state.auth_token()
    if not token:
        raise RuntimeError("buyer_auth_session_missing")
    return BackendClient(get_settings(), token=token)


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "name": "read_runtime_state",
            "description": "Read the current persisted buyer runtime state.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "list_active_grants",
            "description": "List active buyer access grants from the backend.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "import_grant_code",
            "description": "Persist a grant code into local buyer state.",
            "inputSchema": {
                "type": "object",
                "properties": {"grant_code": {"type": "string"}},
                "required": ["grant_code"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_runtime_session",
            "description": "Redeem the active grant into a live runtime session.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "grant_id": {"type": "string"},
                    "grant_code": {"type": "string"},
                    "network_mode": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "refresh_runtime_session",
            "description": "Refresh the current runtime session from the backend.",
            "inputSchema": {
                "type": "object",
                "properties": {"runtime_session_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "wireguard_up",
            "description": "Bring up the buyer WireGuard tunnel for the active runtime session.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "wireguard_down",
            "description": "Bring down the buyer WireGuard tunnel for the active runtime session.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "open_shell",
            "description": "Return the shell URL for the active runtime session.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "sync_workspace",
            "description": "Package and sync a local workspace directory into the active runtime session.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "read_workspace_status",
            "description": "Read the active runtime workspace status.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "submit_task_execution",
            "description": "Submit a minimal shell command to the active runtime session.",
            "inputSchema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
        },
        {
            "name": "tail_task_logs",
            "description": "Read the most recent task logs, or a specific task id if provided.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "max_chars": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    ]


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    normalized = payload if isinstance(payload, dict) else {"result": payload}
    return {
        "content": [{"type": "text", "text": json.dumps(normalized, ensure_ascii=False, indent=2)}],
        "structuredContent": normalized,
        "isError": is_error,
    }


def _invoke_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    state = _load_state()
    if name == "read_runtime_state":
        return state.runtime_snapshot()
    if name == "list_active_grants":
        return refresh_active_grants(state=state, backend_client=_backend_client(state))
    if name == "import_grant_code":
        return import_grant_code(state, str(arguments.get("grant_code") or ""))
    if name == "create_runtime_session":
        return create_runtime_session(
            settings=settings,
            state=state,
            backend_client=_backend_client(state),
            grant_id=arguments.get("grant_id"),
            grant_code=arguments.get("grant_code"),
            network_mode=str(arguments.get("network_mode") or "wireguard"),
        )
    if name == "refresh_runtime_session":
        return refresh_runtime_session(
            state=state,
            backend_client=_backend_client(state),
            runtime_session_id=arguments.get("runtime_session_id"),
        )
    if name == "wireguard_up":
        return wireguard_up(settings=settings, state=state)
    if name == "wireguard_down":
        return wireguard_down(state=state)
    if name == "open_shell":
        return open_shell(state)
    if name == "sync_workspace":
        return sync_workspace_selection(settings=settings, state=state, source_path=arguments.get("path"))
    if name == "read_workspace_status":
        return read_workspace_status(state)
    if name == "submit_task_execution":
        return submit_task_execution(state=state, command=str(arguments.get("command") or ""))
    if name == "tail_task_logs":
        return tail_task_logs(
            state=state,
            task_id=arguments.get("task_id"),
            max_chars=int(arguments.get("max_chars") or 4000),
        )
    raise RuntimeError(f"unknown_tool:{name}")


def _write_message(message: dict[str, Any]) -> None:
    body = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, value = line.decode("utf-8").split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def main() -> None:
    while True:
        message = _read_message()
        if message is None:
            return
        method = message.get("method")
        params = message.get("params") or {}
        message_id = message.get("id")

        if method == "initialize":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "buyer-client-tools", "version": "0.1.0"},
                    },
                }
            )
            continue
        if method == "notifications/initialized":
            continue
        if method == "ping":
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": {}})
            continue
        if method == "tools/list":
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": {"tools": _tool_descriptors()}})
            continue
        if method == "tools/call":
            try:
                result = _invoke_tool(str(params.get("name") or ""), dict(params.get("arguments") or {}))
                body = _tool_result(result)
            except Exception as exc:  # noqa: BLE001
                body = _tool_result({"error": str(exc)}, is_error=True)
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": body})
            continue
        _write_message(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )


if __name__ == "__main__":
    main()
