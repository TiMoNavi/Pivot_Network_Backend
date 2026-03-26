from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.platform import Node, RuntimeAccessSession


class RuntimeBootstrapError(RuntimeError):
    pass


def _candidate_auth_paths(settings: Settings) -> list[Path]:
    paths: list[Path] = []
    if settings.CODEX_AUTH_JSON_PATH:
        paths.append(Path(settings.CODEX_AUTH_JSON_PATH).expanduser().resolve())
    if settings.CODEX_AUTH_JSON_FALLBACK_HOME:
        paths.append((Path.home() / ".codex" / "auth.json").resolve())
    return paths


def load_codex_api_key(settings: Settings) -> tuple[str | None, str | None]:
    if settings.OPENAI_API_KEY:
        return settings.OPENAI_API_KEY, "env:OPENAI_API_KEY"

    for path in _candidate_auth_paths(settings):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        api_key = payload.get("OPENAI_API_KEY")
        if api_key:
            return str(api_key), str(path)
    return None, None


def build_codex_runtime_bootstrap(settings: Settings) -> dict[str, Any]:
    api_key, auth_source = load_codex_api_key(settings)
    if not api_key:
        raise RuntimeBootstrapError("codex_openai_api_key_not_configured")

    return {
        "model_provider": settings.CODEX_MODEL_PROVIDER,
        "model": settings.CODEX_MODEL,
        "review_model": settings.CODEX_REVIEW_MODEL,
        "model_reasoning_effort": settings.CODEX_MODEL_REASONING_EFFORT,
        "disable_response_storage": settings.CODEX_DISABLE_RESPONSE_STORAGE,
        "network_access": settings.CODEX_NETWORK_ACCESS,
        "windows_wsl_setup_acknowledged": settings.CODEX_WINDOWS_WSL_SETUP_ACKNOWLEDGED,
        "model_context_window": settings.CODEX_MODEL_CONTEXT_WINDOW,
        "model_auto_compact_token_limit": settings.CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT,
        "provider": {
            "name": settings.CODEX_PROVIDER_NAME,
            "base_url": settings.CODEX_PROVIDER_BASE_URL,
            "wire_api": settings.CODEX_PROVIDER_WIRE_API,
            "requires_openai_auth": settings.CODEX_PROVIDER_REQUIRES_OPENAI_AUTH,
        },
        "auth": {
            "OPENAI_API_KEY": api_key,
        },
        "auth_source": auth_source,
    }


def _allocate_ipv4_from_node_id(node_id: int, network_cidr: str) -> str:
    network = ipaddress.ip_network(network_cidr, strict=False)
    if network.version != 4:
        raise RuntimeBootstrapError("wireguard_only_ipv4_supported_for_mvp")

    offset = node_id + 9
    address_int = int(network.network_address) + offset
    last_usable = int(network.broadcast_address) - 1
    if address_int > last_usable:
        raise RuntimeBootstrapError("wireguard_network_pool_exhausted")
    return str(ipaddress.ip_address(address_int))


def build_wireguard_bootstrap(settings: Settings, node: Node, client_public_key: str) -> dict[str, Any]:
    if not settings.WIREGUARD_ENABLED:
        raise RuntimeBootstrapError("wireguard_disabled")
    if not settings.WIREGUARD_SERVER_PUBLIC_KEY:
        raise RuntimeBootstrapError("wireguard_server_public_key_not_configured")
    if not settings.WIREGUARD_ENDPOINT_HOST:
        raise RuntimeBootstrapError("wireguard_endpoint_host_not_configured")

    client_ip = _allocate_ipv4_from_node_id(node.id, settings.WIREGUARD_NETWORK_CIDR)
    return {
        "node_id": node.node_key,
        "interface_name": settings.WIREGUARD_INTERFACE,
        "client_public_key": client_public_key,
        "client_address": f"{client_ip}/32",
        "server_endpoint_host": settings.WIREGUARD_ENDPOINT_HOST,
        "server_endpoint_port": settings.WIREGUARD_ENDPOINT_PORT,
        "server_public_key": settings.WIREGUARD_SERVER_PUBLIC_KEY,
        "allowed_ips": settings.WIREGUARD_ALLOWED_IPS,
        "dns": settings.WIREGUARD_DNS or None,
        "persistent_keepalive": settings.WIREGUARD_PERSISTENT_KEEPALIVE,
        "network_cidr": settings.WIREGUARD_NETWORK_CIDR,
        "activation_mode": "profile_only",
        "server_peer_apply_required": True,
    }


def _extract_node_wireguard_ip(node: Node) -> str | None:
    capabilities = node.capabilities or {}
    interfaces = capabilities.get("interfaces") or {}
    for interface_name, entries in interfaces.items():
        if interface_name != "wg-seller":
            continue
        for entry in entries:
            if str(entry.get("family")) == "2" and entry.get("address"):
                return str(entry["address"])
    return None


def build_buyer_wireguard_bootstrap(
    settings: Settings,
    session: RuntimeAccessSession,
    node: Node,
    client_public_key: str,
) -> dict[str, Any]:
    if not settings.WIREGUARD_ENABLED:
        raise RuntimeBootstrapError("wireguard_disabled")
    if not settings.WIREGUARD_SERVER_PUBLIC_KEY:
        raise RuntimeBootstrapError("wireguard_server_public_key_not_configured")
    if not settings.WIREGUARD_ENDPOINT_HOST:
        raise RuntimeBootstrapError("wireguard_endpoint_host_not_configured")

    network = settings.WIREGUARD_BUYER_NETWORK_CIDR
    client_ip = _allocate_ipv4_from_node_id(session.id, network)
    seller_ip = _extract_node_wireguard_ip(node)
    allowed_ips = f"{seller_ip}/32,{settings.WIREGUARD_NETWORK_CIDR}" if seller_ip else settings.WIREGUARD_ALLOWED_IPS
    return {
        "session_id": session.id,
        "interface_name": settings.WIREGUARD_BUYER_INTERFACE,
        "client_public_key": client_public_key,
        "client_address": f"{client_ip}/32",
        "server_endpoint_host": settings.WIREGUARD_ENDPOINT_HOST,
        "server_endpoint_port": settings.WIREGUARD_ENDPOINT_PORT,
        "server_public_key": settings.WIREGUARD_SERVER_PUBLIC_KEY,
        "allowed_ips": allowed_ips,
        "dns": settings.WIREGUARD_DNS or None,
        "persistent_keepalive": settings.WIREGUARD_PERSISTENT_KEEPALIVE,
        "network_cidr": network,
        "seller_wireguard_target": seller_ip,
        "expires_at": session.expires_at,
    }
