from __future__ import annotations

from typing import Any

from seller_client.agent_mcp import (
    configure_environment,
    connect_server_vpn,
    disconnect_server_vpn,
    generate_wireguard_keypair,
    prepare_wireguard_profile,
)

from buyer_client.runtime.api import request_json


def bootstrap_runtime_session_wireguard(
    *,
    backend_url: str,
    buyer_token: str,
    session_id: int,
    state_dir: str,
) -> dict[str, Any]:
    keypair = generate_wireguard_keypair()
    if not keypair["ok"]:
        raise RuntimeError(f"generate_wireguard_keypair_failed: {keypair}")

    response = request_json(
        "POST",
        f"{backend_url.rstrip('/')}/api/v1/buyer/runtime-sessions/{session_id}/wireguard/bootstrap",
        {"client_public_key": keypair["public_key"]},
        token=buyer_token,
        timeout=120,
    )
    if not response["ok"]:
        raise RuntimeError(f"buyer_wireguard_bootstrap_failed: {response['data']}")
    bundle = response["data"]

    configure_environment(
        backend_url=backend_url,
        wireguard_interface=bundle["interface_name"],
        wireguard_endpoint_host=bundle["server_endpoint_host"],
        wireguard_endpoint_port=bundle["server_endpoint_port"],
        state_dir=state_dir,
    )
    prepare_wireguard_profile(
        server_public_key=bundle["server_public_key"],
        client_private_key=keypair["private_key"],
        client_address=bundle["client_address"],
        endpoint_host=bundle["server_endpoint_host"],
        endpoint_port=bundle["server_endpoint_port"],
        allowed_ips=bundle["allowed_ips"],
        interface_name=bundle["interface_name"],
        dns=bundle.get("dns") or "",
        persistent_keepalive=bundle["persistent_keepalive"],
        state_dir=state_dir,
    )
    activate = connect_server_vpn(interface_name=bundle["interface_name"], state_dir=state_dir)
    return {
        "bundle": bundle,
        "keypair": {"public_key": keypair["public_key"]},
        "activation_result": activate,
    }


def disconnect_runtime_session_wireguard(*, state_dir: str, interface_name: str = "wg-buyer") -> dict[str, Any]:
    return disconnect_server_vpn(interface_name=interface_name, state_dir=state_dir)
