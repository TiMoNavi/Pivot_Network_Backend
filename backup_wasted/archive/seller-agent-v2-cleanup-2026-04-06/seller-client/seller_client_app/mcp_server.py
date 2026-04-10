from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from seller_client_app.backend import BackendClient
from seller_client_app.config import get_settings
from seller_client_app.docker_workbench import build_image, generate_dockerfile_template, push_image
from seller_client_app.env_scan import scan_environment


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-file", type=str, default=os.getenv("SELLER_CLIENT_SESSION_FILE"))
    return parser.parse_args()


def _load_session_context(session_file: str | None) -> dict[str, Any]:
    if not session_file:
        raise RuntimeError("SELLER_CLIENT_SESSION_FILE is not set.")
    payload = json.loads(Path(session_file).read_text(encoding="utf-8"))
    return payload


def _backend_client(payload: dict[str, Any]) -> BackendClient:
    settings = get_settings()
    settings = settings.model_copy(
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


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload if isinstance(payload, dict) else {"result": payload},
        "isError": is_error,
    }


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {"name": "scan_env", "description": "Run the local environment scan.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "fetch_backend_policy", "description": "Get the current seller onboarding policy.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "fetch_join_material", "description": "Fetch seller join material from the backend.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "run_swarm_join", "description": "Run docker swarm join using the last fetched join material.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "list_seller_nodes", "description": "List seller nodes from the backend.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {
            "name": "claim_node",
            "description": "Claim a seller node using the onboarding session.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "node_ref": {"type": "string"},
                    "compute_node_id": {"type": "string"},
                    "requested_accelerator": {"type": "string"},
                },
                "required": ["node_ref", "compute_node_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "check_claim_status",
            "description": "Check seller claim status for a node.",
            "inputSchema": {
                "type": "object",
                "properties": {"node_ref": {"type": "string"}},
                "required": ["node_ref"],
                "additionalProperties": False,
            },
        },
        {
            "name": "build_image",
            "description": "Build a constrained seller image from the managed base image.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repository": {"type": "string"},
                    "tag": {"type": "string"},
                    "registry": {"type": "string"},
                    "dockerfile_content": {"type": "string"},
                    "extra_dockerfile_lines": {"type": "array", "items": {"type": "string"}},
                    "resource_profile": {"type": "object"},
                },
                "required": ["repository", "tag", "registry"],
                "additionalProperties": True,
            },
        },
        {
            "name": "push_image",
            "description": "Push an image to the configured registry.",
            "inputSchema": {
                "type": "object",
                "properties": {"image_ref": {"type": "string"}},
                "required": ["image_ref"],
                "additionalProperties": False,
            },
        },
        {
            "name": "report_image",
            "description": "Report an already built and pushed image to the backend.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "node_ref": {"type": "string"},
                    "runtime_image_ref": {"type": "string"},
                    "repository": {"type": "string"},
                    "tag": {"type": "string"},
                    "registry": {"type": "string"},
                },
                "required": ["node_ref", "runtime_image_ref", "repository", "tag", "registry"],
                "additionalProperties": False,
            },
        },
        {"name": "collect_logs", "description": "Collect local log file information for the active session.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    ]


def _local_node_ref() -> str:
    completed = subprocess.run(
        ["docker", "info", "--format", "{{.Swarm.NodeID}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "failed to resolve local swarm node id")
    return completed.stdout.strip()


def _invoke_tool(name: str, arguments: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    backend = _backend_client(payload)
    onboarding = payload.get("onboarding_session") or {}
    session_id = onboarding.get("session_id")
    session_root = Path(payload["workspace_root"]) / settings.session_subdir_name / str(session_id)
    workspace_dir = session_root / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    if name == "scan_env":
        return scan_environment(settings, backend)
    if name == "fetch_backend_policy":
        return onboarding.get("policy") or {}
    if name == "fetch_join_material":
        return backend.get_join_material(
            onboarding.get("requested_accelerator") or "gpu",
            onboarding.get("requested_compute_node_id"),
        )
    if name == "run_swarm_join":
        join_material = payload.get("last_join_material")
        if not join_material:
            raise RuntimeError("No join material has been fetched yet.")
        command = [
            "docker",
            "swarm",
            "join",
            "--token",
            join_material["join_token"],
            f"{join_material['manager_addr']}:{join_material['manager_port']}",
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=120)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "docker swarm join failed")
        return {
            "status": "joined",
            "local_node_ref": _local_node_ref(),
            "stdout": completed.stdout.strip(),
        }
    if name == "list_seller_nodes":
        return {"nodes": backend.list_nodes()}
    if name == "claim_node":
        node_ref = arguments.get("node_ref") or _local_node_ref()
        return backend.claim_node(
            node_ref=node_ref,
            onboarding_session_id=session_id,
            compute_node_id=arguments["compute_node_id"],
            requested_accelerator=arguments.get("requested_accelerator") or onboarding.get("requested_accelerator") or "gpu",
        )
    if name == "check_claim_status":
        return backend.get_claim_status(arguments["node_ref"])
    if name == "build_image":
        policy = onboarding.get("policy") or {}
        dockerfile_content = arguments.get("dockerfile_content") or generate_dockerfile_template(
            policy,
            arguments.get("extra_dockerfile_lines"),
        )
        artifact = build_image(
            settings=settings,
            session_runtime_dir=session_root,
            policy=policy,
            repository=arguments["repository"],
            tag=arguments["tag"],
            registry=arguments["registry"],
            dockerfile_content=dockerfile_content,
            resource_profile=arguments.get("resource_profile"),
        )
        return {
            "image_ref": artifact.image_ref,
            "repository": artifact.repository,
            "tag": artifact.tag,
            "registry": artifact.registry,
            "dockerfile_path": str(artifact.dockerfile_path),
            "metadata_path": str(artifact.metadata_path),
        }
    if name == "push_image":
        push_image(arguments["image_ref"])
        return {"status": "pushed", "image_ref": arguments["image_ref"]}
    if name == "report_image":
        return backend.report_image(
            node_ref=arguments["node_ref"],
            runtime_image_ref=arguments["runtime_image_ref"],
            repository=arguments["repository"],
            tag=arguments["tag"],
            registry=arguments["registry"],
        )
    if name == "collect_logs":
        logs_dir = session_root / "logs"
        files = []
        for file_path in sorted(logs_dir.glob("**/*")):
            if file_path.is_file():
                files.append({"path": str(file_path), "size": file_path.stat().st_size})
        return {"logs": files}
    raise RuntimeError(f"Unknown tool: {name}")


def main() -> None:
    args = _parse_args()
    session_file = args.session_file
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
                        "serverInfo": {"name": "seller-client-tools", "version": "0.1.0"},
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
                payload = _load_session_context(session_file)
                result = _invoke_tool(name, arguments, payload)
                body = _tool_result(result, is_error=False)
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
