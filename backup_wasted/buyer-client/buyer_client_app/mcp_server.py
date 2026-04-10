from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from buyer_client_app.backend import BackendClient
from buyer_client_app.config import get_settings
from buyer_client_app.env_scan import scan_environment
from buyer_client_app.wireguard_client import install_tunnel, remove_tunnel, write_config
from buyer_client_app.workspace_sync import package_workspace, sync_workspace


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-file", type=str, default=os.getenv("BUYER_CLIENT_SESSION_FILE"))
    return parser.parse_args()


def _load_payload(session_file: str | None) -> dict[str, Any]:
    if not session_file:
        raise RuntimeError("BUYER_CLIENT_SESSION_FILE is not set.")
    return json.loads(Path(session_file).read_text(encoding="utf-8"))


def _backend_client(payload: dict[str, Any]) -> BackendClient:
    settings = get_settings().model_copy(
        update={
            "backend_base_url": payload["backend_base_url"],
            "backend_api_prefix": payload["backend_api_prefix"],
        }
    )
    return BackendClient(settings, token=payload.get("auth_token"))


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


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {"name": "scan_env", "description": "Run the buyer local environment scan.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "fetch_catalog", "description": "Fetch buyer catalog offers.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "create_order", "description": "Create a buyer order.", "inputSchema": {"type": "object", "properties": {"offer_id": {"type": "string"}, "requested_duration_minutes": {"type": "integer"}}, "required": ["offer_id", "requested_duration_minutes"], "additionalProperties": False}},
        {"name": "redeem_access_code", "description": "Redeem an access code.", "inputSchema": {"type": "object", "properties": {"access_code": {"type": "string"}}, "required": ["access_code"], "additionalProperties": False}},
        {"name": "fetch_connect_material", "description": "Fetch latest buyer connect material.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "wireguard_up", "description": "Bring up the buyer WireGuard tunnel.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "wireguard_down", "description": "Remove the buyer WireGuard tunnel.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "open_shell_embed", "description": "Return the shell embed URL.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "sync_workspace", "description": "Package and sync the selected local workspace path.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}},
        {"name": "stop_runtime_session", "description": "Stop the buyer runtime session.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "collect_logs", "description": "Collect buyer session logs.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    ]


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload if isinstance(payload, dict) else {"result": payload},
        "isError": is_error,
    }


def _invoke_tool(name: str, arguments: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    backend = _backend_client(payload)
    snapshot = payload.get("snapshot") or {}
    runtime_session = snapshot.get("runtime_session") or {}
    bootstrap = snapshot.get("bootstrap_config") or {}
    runtime_session_id = runtime_session.get("id") or bootstrap.get("runtime_session_id")
    session_root = Path(settings.workspace_root_path) / settings.session_subdir_name / str(runtime_session_id)
    session_root.mkdir(parents=True, exist_ok=True)

    if name == "scan_env":
        return scan_environment(settings, backend)
    if name == "fetch_catalog":
        return {"offers": backend.catalog_offers()}
    if name == "create_order":
        return backend.create_order(arguments["offer_id"], arguments["requested_duration_minutes"])
    if name == "redeem_access_code":
        return backend.redeem_access_code(arguments["access_code"])
    if name == "fetch_connect_material":
        return backend.get_connect_material(runtime_session_id)
    if name == "wireguard_up":
        profile = bootstrap.get("wireguard_profile") or {}
        wireguard_dir = session_root / "wireguard"
        config_path = wireguard_dir / f"{settings.wireguard_tunnel_prefix}-{runtime_session_id[:8]}.conf"
        private_key = bootstrap.get("wireguard_private_key")
        write_config(config_path=config_path, private_key=private_key, profile=profile)
        tunnel_name = install_tunnel(config_path)
        return {"status": "up", "config_path": str(config_path), "tunnel_name": tunnel_name}
    if name == "wireguard_down":
        tunnel_name = f"{settings.wireguard_tunnel_prefix}-{runtime_session_id[:8]}"
        remove_tunnel(tunnel_name)
        return {"status": "down", "tunnel_name": tunnel_name}
    if name == "open_shell_embed":
        return {"shell_embed_url": bootstrap.get("shell_embed_url")}
    if name == "sync_workspace":
        archive_path = package_workspace(Path(arguments["path"]), settings.workspace_archive_name)
        return sync_workspace(
            archive_path,
            bootstrap.get("workspace_sync_url"),
            bootstrap.get("workspace_extract_url"),
        )
    if name == "stop_runtime_session":
        return backend.stop_runtime_session(runtime_session_id)
    if name == "collect_logs":
        return {"session_root": str(session_root)}
    raise RuntimeError(f"Unknown tool: {name}")


def main() -> None:
    args = _parse_args()
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
            name = params.get("name")
            arguments = params.get("arguments") or {}
            try:
                payload = _load_payload(args.session_file)
                result = _invoke_tool(name, arguments, payload)
                body = _tool_result(result, is_error=False)
            except Exception as exc:  # noqa: BLE001
                body = _tool_result({"error": str(exc)}, is_error=True)
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": body})
            continue
        _write_message({"jsonrpc": "2.0", "id": message_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})


if __name__ == "__main__":
    main()
