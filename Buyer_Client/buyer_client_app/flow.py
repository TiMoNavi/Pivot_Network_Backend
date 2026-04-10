from __future__ import annotations

from typing import Any


def build_runtime_access_plan(
    order: dict[str, Any] | None,
    access_grant: dict[str, Any] | None,
) -> dict[str, Any]:
    if order is None and access_grant is None:
        return {
            "status": "idle",
            "purchase_semantics": "runtime_bundle",
            "warnings": [],
            "next_actions": ["list_offers", "create_order", "activate_order"],
        }

    if access_grant is None:
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

    payload = dict(access_grant.get("connect_material_payload") or {})
    gateway_urls = [
        _optional_str(payload.get("gateway_access_url")),
        _optional_str(payload.get("wireguard_gateway_access_url")),
        _optional_str(payload.get("shell_embed_url")),
    ]
    gateway_urls = [url for url in gateway_urls if url]
    has_runtime_entry = bool(gateway_urls)

    runtime_session_id = access_grant.get("runtime_session_id")
    effective_target_addr = _optional_str(payload.get("effective_target_addr"))
    effective_target_source = _optional_str(payload.get("effective_target_source"))
    truth_authority = _optional_str(payload.get("truth_authority"))

    wireguard_profile = {
        "server_public_key": _optional_str(payload.get("server_public_key")),
        "server_access_ip": _optional_str(payload.get("server_access_ip")),
        "endpoint_host": _optional_str(payload.get("endpoint_host")),
        "endpoint_port": payload.get("endpoint_port"),
        "allowed_ips": list(payload.get("allowed_ips") or []),
        "client_allowed_ips": list(payload.get("client_allowed_ips") or []),
        "persistent_keepalive": payload.get("persistent_keepalive"),
        "client_address": _optional_str(payload.get("client_address")),
    }
    has_wireguard_material = any(
        (
            wireguard_profile["server_public_key"],
            wireguard_profile["server_access_ip"],
            wireguard_profile["client_address"],
        )
    )

    warnings: list[str] = []
    next_actions: list[str] = []
    status = "ready"

    if not has_runtime_entry:
        status = "pending_runtime_bundle"
        next_actions.append("wait_for_bundle_connect_metadata")
        warnings.append("当前 grant 还没有 gateway/runtime 的正式接入材料。")

    if effective_target_addr and not has_runtime_entry:
        warnings.append(
            "当前 backend 仅返回 effective_target 证据；买家侧不应直接把它当正式入口。"
        )
        next_actions.append("treat_effective_target_as_diagnostic_only")

    if has_wireguard_material:
        next_actions.append("materialize_wireguard_profile")

    if has_runtime_entry:
        next_actions.extend(["verify_gateway_reachability", "open_runtime_shell"])

    next_actions = list(dict.fromkeys(next_actions))

    return {
        "status": status,
        "purchase_semantics": "runtime_bundle",
        "order_id": None if order is None else order.get("id"),
        "offer_id": None if order is None else order.get("offer_id"),
        "runtime_session_id": runtime_session_id,
        "grant_id": access_grant.get("id"),
        "grant_status": access_grant.get("status"),
        "grant_type": access_grant.get("grant_type"),
        "swarm_bundle": {
            "session_id": runtime_session_id,
            "runtime_service_name": _optional_str(payload.get("runtime_service_name")),
            "gateway_service_name": _optional_str(payload.get("gateway_service_name")),
            "network_name": _optional_str(payload.get("network_name")),
            "access_mode": _optional_str(payload.get("access_mode")),
        },
        "network_entry": {
            "mode": "wireguard" if has_wireguard_material else _optional_str(payload.get("network_mode")) or "unknown",
            "gateway_access_url": _optional_str(payload.get("gateway_access_url")),
            "public_gateway_access_url": _optional_str(payload.get("public_gateway_access_url")),
            "wireguard_gateway_access_url": _optional_str(payload.get("wireguard_gateway_access_url")),
            "shell_embed_url": _optional_str(payload.get("shell_embed_url")),
            "workspace_sync_url": _optional_str(payload.get("workspace_sync_url")),
            "workspace_extract_url": _optional_str(payload.get("workspace_extract_url")),
            "workspace_status_url": _optional_str(payload.get("workspace_status_url")),
        },
        "wireguard_profile": wireguard_profile,
        "truth_lane": {
            "grant_mode": _optional_str(payload.get("grant_mode")),
            "effective_target_addr": effective_target_addr,
            "effective_target_source": effective_target_source,
            "truth_authority": truth_authority,
            "raw_manager_acceptance_status": _optional_str(payload.get("raw_manager_acceptance_status")),
            "minimum_tcp_validation": payload.get("minimum_tcp_validation") or {},
        },
        "warnings": warnings,
        "next_actions": next_actions,
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
