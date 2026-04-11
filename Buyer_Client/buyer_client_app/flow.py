from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse


def build_runtime_access_plan(
    order: dict[str, Any] | None,
    access_grant: dict[str, Any] | None,
    runtime_session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if order is None and access_grant is None and runtime_session is None:
        return {
            "status": "idle",
            "purchase_semantics": "runtime_bundle",
            "warnings": [],
            "next_actions": ["list_offers", "create_order", "activate_order"],
        }

    if access_grant is None and runtime_session is None:
        return {
            "status": "await_order_activation",
            "purchase_semantics": "runtime_bundle",
            "order_id": None if order is None else order.get("id"),
            "warnings": [
                "订单已创建，但尚未生成 access grant。",
                "正式语义上，此阶段仍未完成 swarm runtime bundle 编排。",
            ],
            "next_actions": ["activate_order"],
        }

    grant_payload = dict((access_grant or {}).get("connect_material_payload") or {})
    connect_metadata = dict((runtime_session or {}).get("connect_metadata") or {})
    wireguard_lease_metadata = dict((runtime_session or {}).get("wireguard_lease_metadata") or {})

    gateway_access_url = _first_non_empty(
        connect_metadata.get("gateway_access_url"),
        grant_payload.get("gateway_access_url"),
    )
    public_gateway_access_url = _first_non_empty(
        connect_metadata.get("public_gateway_access_url"),
        grant_payload.get("public_gateway_access_url"),
    )
    wireguard_gateway_access_url = _first_non_empty(
        connect_metadata.get("wireguard_gateway_access_url"),
        grant_payload.get("wireguard_gateway_access_url"),
    )
    shell_embed_url = _first_non_empty(
        connect_metadata.get("wireguard_shell_embed_url"),
        connect_metadata.get("shell_embed_url"),
        grant_payload.get("wireguard_shell_embed_url"),
        grant_payload.get("shell_embed_url"),
        _replace_url_path(wireguard_gateway_access_url, "/shell/"),
        _replace_url_path(gateway_access_url, "/shell/"),
    )
    workspace_sync_url = _first_non_empty(
        connect_metadata.get("workspace_sync_url"),
        grant_payload.get("workspace_sync_url"),
        _replace_url_path(shell_embed_url, "/api/workspace/upload"),
        _replace_url_path(gateway_access_url, "/api/workspace/upload"),
    )
    workspace_extract_url = _first_non_empty(
        connect_metadata.get("workspace_extract_url"),
        grant_payload.get("workspace_extract_url"),
        _replace_url_path(workspace_sync_url, "/api/workspace/extract"),
        _replace_url_path(shell_embed_url, "/api/workspace/extract"),
    )
    workspace_status_url = _first_non_empty(
        connect_metadata.get("workspace_status_url"),
        grant_payload.get("workspace_status_url"),
        _replace_url_path(workspace_sync_url, "/api/workspace/status"),
        _replace_url_path(shell_embed_url, "/api/workspace/status"),
    )
    task_exec_url = _first_non_empty(
        connect_metadata.get("task_exec_url"),
        connect_metadata.get("exec_url"),
        grant_payload.get("task_exec_url"),
        grant_payload.get("exec_url"),
        _replace_url_path(shell_embed_url, "/api/exec"),
        _replace_url_path(gateway_access_url, "/api/exec"),
    )

    runtime_session_id = _first_non_empty(
        (runtime_session or {}).get("id"),
        (access_grant or {}).get("runtime_session_id"),
        grant_payload.get("runtime_session_id"),
    )
    effective_target_addr = _optional_str(grant_payload.get("effective_target_addr"))
    effective_target_source = _optional_str(grant_payload.get("effective_target_source"))
    truth_authority = _optional_str(grant_payload.get("truth_authority"))

    client_address = _optional_str(
        wireguard_lease_metadata.get("client_address"),
    ) or _optional_str(grant_payload.get("client_address"))
    if client_address and "/" not in client_address:
        client_address = f"{client_address}/32"

    peer_allowed_ips = list(
        wireguard_lease_metadata.get("client_allowed_ips")
        or grant_payload.get("client_allowed_ips")
        or wireguard_lease_metadata.get("allowed_ips")
        or grant_payload.get("allowed_ips")
        or []
    )
    if not peer_allowed_ips:
        server_access_ip = _optional_str(
            wireguard_lease_metadata.get("server_access_ip"),
        ) or _optional_str(grant_payload.get("server_access_ip"))
        if server_access_ip:
            peer_allowed_ips = [f"{server_access_ip}/32"]

    wireguard_profile = {
        "server_public_key": _optional_str(
            wireguard_lease_metadata.get("server_public_key"),
        ) or _optional_str(grant_payload.get("server_public_key")),
        "server_access_ip": _optional_str(
            wireguard_lease_metadata.get("server_access_ip"),
        ) or _optional_str(grant_payload.get("server_access_ip")),
        "endpoint_host": _optional_str(
            wireguard_lease_metadata.get("endpoint_host"),
        ) or _optional_str(grant_payload.get("endpoint_host")),
        "endpoint_port": wireguard_lease_metadata.get("endpoint_port") or grant_payload.get("endpoint_port"),
        "allowed_ips": peer_allowed_ips,
        "client_allowed_ips": list(
            wireguard_lease_metadata.get("client_allowed_ips")
            or grant_payload.get("client_allowed_ips")
            or []
        ),
        "persistent_keepalive": wireguard_lease_metadata.get("persistent_keepalive")
        or grant_payload.get("persistent_keepalive"),
        "client_address": client_address,
    }
    has_wireguard_material = all(
        (
            wireguard_profile["server_public_key"],
            wireguard_profile["endpoint_host"],
            wireguard_profile["endpoint_port"],
            wireguard_profile["client_address"],
        )
    )
    has_wireguard_hint = any(
        (
            wireguard_profile["server_public_key"],
            wireguard_profile["server_access_ip"],
            wireguard_profile["client_address"],
        )
    )

    has_runtime_entry = any(
        (
            shell_embed_url,
            workspace_sync_url,
            task_exec_url,
            gateway_access_url,
            wireguard_gateway_access_url,
        )
    )
    runtime_session_status = _optional_str((runtime_session or {}).get("status"))
    runtime_bundle_status = _optional_str((runtime_session or {}).get("runtime_bundle_status"))

    warnings: list[str] = []
    next_actions: list[str] = []

    if runtime_session is not None:
        status = runtime_session_status or _bundle_status_to_state(runtime_bundle_status)
        if status == "ready" and not has_runtime_entry:
            status = "pending_runtime_bundle"
        if status in {"allocating", "created"}:
            next_actions.append("refresh_runtime_session")
        elif status == "failed":
            next_actions.append("inspect_runtime_errors")
        elif status == "closed":
            next_actions.append("create_runtime_session")
    elif has_runtime_entry:
        status = "ready"
    else:
        status = "pending_runtime_bundle"
        next_actions.append("create_runtime_session")
        if access_grant is not None:
            next_actions.append("wait_for_bundle_connect_metadata")

    if not has_runtime_entry:
        warnings.append("当前 runtime session 还没有完整的 shell/workspace/task 接入材料。")

    if effective_target_addr and not has_runtime_entry:
        warnings.append("当前 backend 仅返回 effective_target 证据；买家侧不应直接把它当正式入口。")
        next_actions.append("treat_effective_target_as_diagnostic_only")

    if has_wireguard_material:
        next_actions.append("wireguard_up")

    if shell_embed_url:
        next_actions.append("open_runtime_shell")
    if workspace_sync_url and workspace_extract_url:
        next_actions.append("sync_workspace")
    if task_exec_url:
        next_actions.append("submit_task_execution")

    next_actions = list(dict.fromkeys(next_actions))

    return {
        "status": status,
        "purchase_semantics": "runtime_bundle",
        "order_id": None if order is None else order.get("id"),
        "offer_id": _first_non_empty(
            None if order is None else order.get("offer_id"),
            (runtime_session or {}).get("offer_id"),
        ),
        "runtime_session_id": runtime_session_id,
        "runtime_session_status": runtime_session_status,
        "runtime_bundle_status": runtime_bundle_status,
        "grant_id": None if access_grant is None else access_grant.get("id"),
        "grant_status": None if access_grant is None else access_grant.get("status"),
        "grant_type": None if access_grant is None else access_grant.get("grant_type"),
        "swarm_bundle": {
            "session_id": runtime_session_id,
            "runtime_service_name": _first_non_empty(
                (runtime_session or {}).get("runtime_service_name"),
                grant_payload.get("runtime_service_name"),
            ),
            "gateway_service_name": _first_non_empty(
                (runtime_session or {}).get("gateway_service_name"),
                grant_payload.get("gateway_service_name"),
            ),
            "network_name": _first_non_empty(
                (runtime_session or {}).get("network_name"),
                grant_payload.get("network_name"),
            ),
            "access_mode": _optional_str(grant_payload.get("access_mode")),
        },
        "network_entry": {
            "mode": "wireguard" if has_wireguard_hint else _optional_str(grant_payload.get("network_mode")) or "unknown",
            "gateway_access_url": gateway_access_url,
            "public_gateway_access_url": public_gateway_access_url,
            "wireguard_gateway_access_url": wireguard_gateway_access_url,
            "shell_embed_url": shell_embed_url,
            "workspace_sync_url": workspace_sync_url,
            "workspace_extract_url": workspace_extract_url,
            "workspace_status_url": workspace_status_url,
            "task_exec_url": task_exec_url,
        },
        "wireguard_profile": wireguard_profile,
        "truth_lane": {
            "grant_mode": _optional_str(grant_payload.get("grant_mode")),
            "effective_target_addr": effective_target_addr,
            "effective_target_source": effective_target_source,
            "truth_authority": truth_authority,
            "raw_manager_acceptance_status": _optional_str(grant_payload.get("raw_manager_acceptance_status")),
            "minimum_tcp_validation": grant_payload.get("minimum_tcp_validation") or {},
        },
        "warnings": warnings,
        "next_actions": next_actions,
    }


def _bundle_status_to_state(runtime_bundle_status: str | None) -> str:
    lowered = str(runtime_bundle_status or "").strip().lower()
    if lowered == "running":
        return "ready"
    if lowered in {"created", "provisioning", "allocated"}:
        return "allocating"
    if lowered == "failed":
        return "failed"
    if lowered == "removed":
        return "closed"
    return lowered or "created"


def _replace_url_path(url: Any, path: str) -> str | None:
    cleaned = _optional_str(url)
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return None
    normalized_path = path if path.startswith("/") else f"/{path}"
    return urlunparse((parsed.scheme, parsed.netloc, normalized_path, "", "", ""))


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        cleaned = _optional_str(value)
        if cleaned:
            return cleaned
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
