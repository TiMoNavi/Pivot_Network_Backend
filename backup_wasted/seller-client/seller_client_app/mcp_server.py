from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from seller_client_app.automation import sell_my_compute_full_auto
from seller_client_app.backend import BackendClient
from seller_client_app.config import get_settings
from seller_client_app.env_scan import scan_environment
from seller_client_app.ubuntu_compute import (
    bootstrap_ubuntu_compute,
    collect_wireguard_node_status,
    detect_ubuntu_swarm_info,
    detect_ubuntu_swarm_node_ref,
    join_swarm_from_ubuntu,
    scan_ubuntu_compute,
    sync_context_to_ubuntu,
)
from seller_client_app.ubuntu_image_builder import (
    build_image_in_ubuntu,
    generate_dockerfile_template,
    push_image_from_ubuntu,
)
from seller_client_app.ubuntu_standard_image import pull_standard_image, verify_standard_image
from seller_client_app.windows_host import run_windows_host_install_and_check


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-file", type=str, default=os.getenv("SELLER_CLIENT_SESSION_FILE"))
    return parser.parse_args()


def _load_session_context(session_file: str | None) -> dict[str, Any]:
    if not session_file:
        raise RuntimeError("SELLER_CLIENT_SESSION_FILE is not set.")
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


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload if isinstance(payload, dict) else {"result": payload},
        "isError": is_error,
    }


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "name": "install_windows_host",
            "description": "Run the first-run Windows seller host install/check script in administrator mode.",
            "inputSchema": {
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["check", "install", "all"]}},
                "additionalProperties": False,
            },
        },
        {
            "name": "scan_windows_host",
            "description": "Run the structured Windows host environment scan.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "bootstrap_ubuntu_compute",
            "description": "Fetch Ubuntu bootstrap config and execute it inside the configured WSL Ubuntu distribution.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pull_swarm_standard_image",
            "description": "Pull the backend-provided seller swarm standard image in Ubuntu Docker.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "verify_swarm_standard_image",
            "description": "Verify the backend-provided seller swarm standard image in Ubuntu, including GPU, Python, WireGuard, Docker, and manager network reachability.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "sync_context_to_ubuntu",
            "description": "Copy a Windows build context into the Ubuntu compute workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "local_source_path": {"type": "string"},
                    "ubuntu_target_path": {"type": "string"},
                },
                "required": ["local_source_path"],
                "additionalProperties": False,
            },
        },
        {
            "name": "join_swarm_from_ubuntu_host",
            "description": "Run docker swarm join on the Ubuntu host Docker CLI with the backend-provided WireGuard advertise/data-path addresses.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "mark_compute_ready",
            "description": "Mark the Ubuntu compute node as ready only after local NodeAddr matches the expected WireGuard address.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "claim_node",
            "description": "Claim the current Ubuntu Swarm node in the platform.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "node_ref": {"type": "string"},
                    "compute_node_id": {"type": "string"},
                    "requested_accelerator": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "show_wireguard_node_status",
            "description": "Show local and platform NodeAddr values and whether they match the expected WireGuard address.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "build_image_in_ubuntu",
            "description": "Build a constrained seller runtime image inside Ubuntu Docker Engine.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repository": {"type": "string"},
                    "tag": {"type": "string"},
                    "registry": {"type": "string"},
                    "ubuntu_context_path": {"type": "string"},
                    "dockerfile_content": {"type": "string"},
                    "extra_dockerfile_lines": {"type": "array", "items": {"type": "string"}},
                    "resource_profile": {"type": "object"},
                },
                "required": ["repository", "tag", "registry"],
                "additionalProperties": True,
            },
        },
        {
            "name": "push_image_from_ubuntu",
            "description": "Push a runtime image from the Ubuntu Docker Engine.",
            "inputSchema": {
                "type": "object",
                "properties": {"image_ref": {"type": "string"}},
                "required": ["image_ref"],
                "additionalProperties": False,
            },
        },
        {
            "name": "report_image",
            "description": "Report an already built and pushed image to the platform backend.",
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
        {
            "name": "sell_my_compute_full_auto",
            "description": "Run the full seller compute enablement flow: Windows install/check, Ubuntu bootstrap, standard image pull/verify, join, WireGuard NodeAddr check, compute-ready, and claim.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


def _invoke_tool(name: str, arguments: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    backend = _backend_client(payload)
    onboarding = payload.get("onboarding_session") or {}
    session_id = onboarding.get("session_id")
    if name not in {"install_windows_host", "scan_windows_host"} and not session_id:
        raise RuntimeError("Onboarding session is not initialized.")

    session_root = Path(payload.get("workspace_root") or settings.workspace_root) / settings.session_subdir_name / str(session_id or "window")
    session_root.mkdir(parents=True, exist_ok=True)

    if name == "install_windows_host":
        mode = arguments.get("mode") or "all"
        output_path = session_root / "logs" / "windows-host-install-and-check.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return run_windows_host_install_and_check(settings, mode=mode, output_path=output_path)

    if name == "scan_windows_host":
        return scan_environment(settings, backend)

    if name == "bootstrap_ubuntu_compute":
        ubuntu_bootstrap = backend.get_ubuntu_bootstrap(session_id)
        return {
            "bootstrap": ubuntu_bootstrap,
            "result": bootstrap_ubuntu_compute(settings, ubuntu_bootstrap),
        }

    if name == "pull_swarm_standard_image":
        ubuntu_bootstrap = backend.get_ubuntu_bootstrap(session_id)
        return pull_standard_image(settings, ubuntu_bootstrap)

    if name == "verify_swarm_standard_image":
        ubuntu_bootstrap = backend.get_ubuntu_bootstrap(session_id)
        return verify_standard_image(
            settings,
            ubuntu_bootstrap,
            session_id=session_id,
            requested_accelerator=onboarding.get("requested_accelerator") or "gpu",
        )

    if name == "sync_context_to_ubuntu":
        return sync_context_to_ubuntu(
            settings,
            arguments["local_source_path"],
            arguments.get("ubuntu_target_path"),
        )

    if name == "join_swarm_from_ubuntu_host":
        ubuntu_bootstrap = backend.get_ubuntu_bootstrap(session_id)
        result = join_swarm_from_ubuntu(settings, ubuntu_bootstrap)
        return {
            **result,
            "node_ref": detect_ubuntu_swarm_node_ref(settings),
            "swarm_info": detect_ubuntu_swarm_info(settings),
        }

    if name == "mark_compute_ready":
        ubuntu_bootstrap = backend.get_ubuntu_bootstrap(session_id)
        node_ref = detect_ubuntu_swarm_node_ref(settings)
        node_status = collect_wireguard_node_status(
            settings,
            expected_node_addr=ubuntu_bootstrap["ubuntu_compute_bootstrap"]["expected_node_addr"],
            backend_client=backend,
            node_ref=node_ref,
        )
        if not node_status["wireguard_addr_match"]:
            raise RuntimeError("NodeAddr is not the expected WireGuard address yet.")
        return backend.post_compute_ready(
            session_id,
            {
                "node_ref": node_ref,
                "swarm_info": detect_ubuntu_swarm_info(settings),
                "node_status": node_status,
            },
        )

    if name == "claim_node":
        node_ref = arguments.get("node_ref") or detect_ubuntu_swarm_node_ref(settings)
        compute_node_id = arguments.get("compute_node_id") or onboarding.get("requested_compute_node_id")
        if not compute_node_id:
            raise RuntimeError("compute_node_id is required before claiming the node.")
        requested_accelerator = arguments.get("requested_accelerator") or onboarding.get("requested_accelerator") or "gpu"
        return backend.claim_node(
            node_ref=node_ref,
            onboarding_session_id=session_id,
            compute_node_id=compute_node_id,
            requested_accelerator=requested_accelerator,
        )

    if name == "show_wireguard_node_status":
        ubuntu_bootstrap = backend.get_ubuntu_bootstrap(session_id)
        return collect_wireguard_node_status(
            settings,
            expected_node_addr=ubuntu_bootstrap["ubuntu_compute_bootstrap"]["expected_node_addr"],
            backend_client=backend,
        )

    if name == "build_image_in_ubuntu":
        policy = onboarding.get("policy") or {}
        if not policy:
            raise RuntimeError("Onboarding policy is missing.")
        dockerfile_content = arguments.get("dockerfile_content") or generate_dockerfile_template(
            policy,
            arguments.get("extra_dockerfile_lines"),
        )
        ubuntu_context_path = arguments.get("ubuntu_context_path") or settings.ubuntu_workspace_root
        artifact = build_image_in_ubuntu(
            settings=settings,
            session_runtime_dir=session_root,
            policy=policy,
            repository=arguments["repository"],
            tag=arguments["tag"],
            registry=arguments["registry"],
            dockerfile_content=dockerfile_content,
            ubuntu_context_path=ubuntu_context_path,
            resource_profile=arguments.get("resource_profile"),
        )
        return {
            "image_ref": artifact.image_ref,
            "repository": artifact.repository,
            "tag": artifact.tag,
            "registry": artifact.registry,
            "ubuntu_context_path": artifact.ubuntu_context_path,
            "ubuntu_dockerfile_path": artifact.ubuntu_dockerfile_path,
            "dockerfile_path": str(artifact.local_dockerfile_path),
            "metadata_path": str(artifact.local_metadata_path),
        }

    if name == "push_image_from_ubuntu":
        push_image_from_ubuntu(settings, arguments["image_ref"])
        return {"status": "pushed", "image_ref": arguments["image_ref"], "executor": "wsl_ubuntu"}

    if name == "report_image":
        return backend.report_image(
            node_ref=arguments["node_ref"],
            runtime_image_ref=arguments["runtime_image_ref"],
            repository=arguments["repository"],
            tag=arguments["tag"],
            registry=arguments["registry"],
        )

    if name == "sell_my_compute_full_auto":
        return sell_my_compute_full_auto(
            settings=settings,
            backend_client=backend,
            onboarding_session=onboarding,
        )

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
                        "serverInfo": {"name": "seller-client-tools", "version": "0.3.0"},
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
