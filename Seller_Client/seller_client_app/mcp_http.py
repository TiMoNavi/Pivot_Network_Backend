from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from seller_client_app.config import Settings
from seller_client_app.mcp_server import (
    _append_mcp_log,
    _invoke_tool,
    _load_session_context,
    _tool_descriptors,
    _tool_result,
)

HTTP_MCP_BEARER_ENV_VAR = "SELLER_CLIENT_MCP_HTTP_BEARER"
DEFAULT_PROTOCOL_VERSION = "2025-03-26"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-03-26",
    "2024-11-05",
)


@dataclass(slots=True)
class McpHttpResponse:
    status_code: int
    body: dict[str, Any] | str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str | None = None


def mcp_http_url(settings: Settings, session_id: str) -> str:
    return f"http://{_loopback_host(settings)}:{settings.app_port}/local-api/mcp/{quote(session_id, safe='')}"


def ensure_http_mcp_bearer_token(settings: Settings, session_id: str) -> str:
    token_path = _token_path(settings, session_id)
    if token_path.exists():
        existing = token_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    token_path.write_text(token, encoding="utf-8")
    return token


def read_http_mcp_bearer_token(settings: Settings, session_id: str) -> str | None:
    token_path = _token_path(settings, session_id)
    if not token_path.exists():
        return None
    token = token_path.read_text(encoding="utf-8").strip()
    return token or None


def build_mcp_http_get_response(
    *,
    settings: Settings,
    session_id: str,
    headers: Mapping[str, str],
) -> McpHttpResponse:
    normalized_headers = _normalize_headers(headers)
    origin_error = _validate_origin(settings, normalized_headers)
    if origin_error is not None:
        return origin_error
    session_file = _session_file_path(settings, session_id)
    if not session_file.exists():
        return _jsonrpc_http_error(
            status_code=404,
            code=-32004,
            message="Session file not found for MCP request.",
        )
    _append_mcp_log(
        str(session_file),
        f"http_get_stream_open accept={normalized_headers.get('accept', '')} auth={'present' if normalized_headers.get('authorization') else 'missing'}",
    )
    return McpHttpResponse(
        status_code=200,
        headers={
            "MCP-Protocol-Version": DEFAULT_PROTOCOL_VERSION,
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
        body="id: 0\ndata:\n\n",
        media_type="text/event-stream",
    )


def build_mcp_http_delete_response(
    *,
    settings: Settings,
    session_id: str,
    headers: Mapping[str, str],
) -> McpHttpResponse:
    normalized_headers = _normalize_headers(headers)
    auth_error = _authorize_request(settings, session_id, normalized_headers)
    if auth_error is not None:
        return auth_error
    origin_error = _validate_origin(settings, normalized_headers)
    if origin_error is not None:
        return origin_error
    _append_mcp_log(str(_session_file_path(settings, session_id)), "http_delete_not_supported")
    return McpHttpResponse(status_code=405)


def build_mcp_http_post_response(
    *,
    settings: Settings,
    session_id: str,
    headers: Mapping[str, str],
    body: bytes,
) -> McpHttpResponse:
    normalized_headers = _normalize_headers(headers)
    auth_error = _authorize_request(settings, session_id, normalized_headers)
    if auth_error is not None:
        return auth_error
    origin_error = _validate_origin(settings, normalized_headers)
    if origin_error is not None:
        return origin_error

    session_file = _session_file_path(settings, session_id)
    if not session_file.exists():
        return _jsonrpc_http_error(
            status_code=404,
            code=-32004,
            message="Session file not found for MCP request.",
        )

    try:
        message = json.loads(body.decode("utf-8"))
    except Exception as exc:
        _append_mcp_log(str(session_file), f"http_bad_json error={exc}")
        return _jsonrpc_http_error(
            status_code=400,
            code=-32700,
            message="Invalid JSON body for MCP request.",
        )

    if not isinstance(message, dict):
        return _jsonrpc_http_error(
            status_code=400,
            code=-32600,
            message="MCP request body must be a JSON object.",
        )

    protocol_response = _resolve_protocol_version(normalized_headers, message)
    if protocol_response is not None:
        return protocol_response

    protocol_version = _negotiated_protocol_version(normalized_headers, message)
    response_headers = {"MCP-Protocol-Version": protocol_version}
    message_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    _append_mcp_log(
        str(session_file),
        f"http_recv method={method} id={message_id} protocol={protocol_version} accept={normalized_headers.get('accept', '')}",
    )

    if method == "initialize":
        body_payload = {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "seller-client-tools", "version": "0.3.0"},
            },
        }
        response_headers = dict(response_headers)
        response_headers["MCP-Session-Id"] = session_id
        return _jsonrpc_success_response(
            headers=normalized_headers,
            protocol_headers=response_headers,
            protocol_version=protocol_version,
            body_payload=body_payload,
            prefer_sse=_should_use_sse(normalized_headers, protocol_version),
        )

    if message_id is None:
        if method == "notifications/initialized":
            _append_mcp_log(str(session_file), "http_initialized_notification")
        else:
            _append_mcp_log(str(session_file), f"http_notification method={method}")
        return McpHttpResponse(status_code=202, headers=response_headers)

    if method == "ping":
        return _jsonrpc_success_response(
            headers=normalized_headers,
            protocol_headers=response_headers,
            protocol_version=protocol_version,
            body_payload={"jsonrpc": "2.0", "id": message_id, "result": {}},
            prefer_sse=_should_use_sse(normalized_headers, protocol_version),
        )

    if method == "tools/list":
        return _jsonrpc_success_response(
            headers=normalized_headers,
            protocol_headers=response_headers,
            protocol_version=protocol_version,
            body_payload={"jsonrpc": "2.0", "id": message_id, "result": {"tools": _tool_descriptors()}},
            prefer_sse=_should_use_sse(normalized_headers, protocol_version),
        )

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            payload = _load_session_context(str(session_file))
            result = _invoke_tool(str(tool_name), arguments, payload, str(session_file))
            body_payload = _tool_result(result, is_error=False)
            _append_mcp_log(str(session_file), f"http_tools_call_ok name={tool_name}")
        except Exception as exc:
            body_payload = _tool_result({"error": str(exc)}, is_error=True)
            _append_mcp_log(str(session_file), f"http_tools_call_error name={tool_name} error={exc}")
        return _jsonrpc_success_response(
            headers=normalized_headers,
            protocol_headers=response_headers,
            protocol_version=protocol_version,
            body_payload={"jsonrpc": "2.0", "id": message_id, "result": body_payload},
            prefer_sse=_should_use_sse(normalized_headers, protocol_version),
        )

    _append_mcp_log(str(session_file), f"http_method_not_found method={method}")
    return McpHttpResponse(
        status_code=200,
        headers=response_headers,
        body={
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        },
    )


def _normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _authorize_request(settings: Settings, session_id: str, headers: Mapping[str, str]) -> McpHttpResponse | None:
    expected = read_http_mcp_bearer_token(settings, session_id)
    if expected is None:
        return None
    authorization = str(headers.get("authorization") or "").strip()
    if authorization == f"Bearer {expected}":
        return None
    return _jsonrpc_http_error(
        status_code=401,
        code=-32001,
        message="Missing or invalid bearer token for local MCP access.",
    )


def _validate_origin(settings: Settings, headers: Mapping[str, str]) -> McpHttpResponse | None:
    origin = str(headers.get("origin") or "").strip()
    if not origin:
        return None
    allowed_origins = {
        f"http://127.0.0.1:{settings.app_port}",
        f"http://localhost:{settings.app_port}",
        "http://127.0.0.1",
        "http://localhost",
    }
    if origin in allowed_origins:
        return None
    return _jsonrpc_http_error(
        status_code=403,
        code=-32003,
        message="Origin is not allowed for the local MCP endpoint.",
    )


def _resolve_protocol_version(headers: Mapping[str, str], message: Mapping[str, Any]) -> McpHttpResponse | None:
    requested = _requested_protocol_version(headers, message)
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return None
    return _jsonrpc_http_error(
        status_code=400,
        code=-32602,
        message="Unsupported protocol version",
        data={"supported": list(SUPPORTED_PROTOCOL_VERSIONS), "requested": requested},
    )


def _requested_protocol_version(headers: Mapping[str, str], message: Mapping[str, Any]) -> str:
    params = message.get("params") or {}
    if message.get("method") == "initialize":
        protocol_version = params.get("protocolVersion")
        if isinstance(protocol_version, str) and protocol_version.strip():
            return protocol_version.strip()
    header_value = str(headers.get("mcp-protocol-version") or "").strip()
    if header_value:
        return header_value
    return DEFAULT_PROTOCOL_VERSION


def _negotiated_protocol_version(headers: Mapping[str, str], message: Mapping[str, Any]) -> str:
    requested = _requested_protocol_version(headers, message)
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return DEFAULT_PROTOCOL_VERSION


def _jsonrpc_http_error(
    *,
    status_code: int,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> McpHttpResponse:
    error_payload: dict[str, Any] = {"code": code, "message": message}
    if data:
        error_payload["data"] = data
    return McpHttpResponse(
        status_code=status_code,
        headers={"MCP-Protocol-Version": DEFAULT_PROTOCOL_VERSION},
        body={"jsonrpc": "2.0", "error": error_payload},
        media_type="application/json",
    )


def _jsonrpc_success_response(
    *,
    headers: Mapping[str, str],
    protocol_headers: Mapping[str, str],
    protocol_version: str,
    body_payload: dict[str, Any],
    prefer_sse: bool,
) -> McpHttpResponse:
    if prefer_sse:
        event_body = _sse_payload(body_payload)
        response_headers = dict(protocol_headers)
        response_headers.setdefault("Cache-Control", "no-store")
        response_headers.setdefault("Connection", "keep-alive")
        response_headers.setdefault("X-Accel-Buffering", "no")
        return McpHttpResponse(
            status_code=200,
            headers=response_headers,
            body=event_body,
            media_type="text/event-stream",
        )
    return McpHttpResponse(
        status_code=200,
        headers=dict(protocol_headers),
        body=body_payload,
        media_type="application/json",
    )


def _should_use_sse(headers: Mapping[str, str], protocol_version: str) -> bool:
    del headers, protocol_version
    return False


def _sse_payload(message: dict[str, Any]) -> str:
    json_payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    return f"id: 1\ndata:\n\nid: 2\nretry: 3000\ndata: {json_payload}\n\n"


def _token_path(settings: Settings, session_id: str) -> Path:
    return _session_root(settings, session_id) / "mcp-http-token.txt"


def _session_file_path(settings: Settings, session_id: str) -> Path:
    return _session_root(settings, session_id) / "session.json"


def _session_root(settings: Settings, session_id: str) -> Path:
    return settings.workspace_root_path / settings.session_subdir_name / session_id


def _loopback_host(settings: Settings) -> str:
    if settings.app_host in {"127.0.0.1", "localhost"}:
        return settings.app_host
    return "127.0.0.1"
