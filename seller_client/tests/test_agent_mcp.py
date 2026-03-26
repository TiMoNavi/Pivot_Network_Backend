import json
from pathlib import Path

from seller_client.agent_mcp import (
    _build_remote_image_ref,
    _config_path,
    _wireguard_config_path,
    bootstrap_wireguard_from_platform,
    connect_server_vpn,
    configure_environment,
    ensure_joined_to_platform_swarm,
    explain_seller_intent,
    environment_check,
    fetch_codex_runtime_bootstrap,
    fetch_swarm_worker_join_token,
    get_client_config,
    ping,
    prepare_wireguard_profile,
)


def test_ping_returns_ok_payload() -> None:
    response = ping()

    assert response["status"] == "ok"
    assert response["agent"] == "seller-node-agent"


def test_environment_check_includes_expected_keys() -> None:
    response = environment_check()

    assert "docker_cli" in response
    assert "python" in response
    assert "current_workdir" in response


def test_configure_environment_writes_client_config(tmp_path: Path) -> None:
    response = configure_environment(
        manager_host="example.com",
        registry="registry.example.com:5000",
        portainer_url="https://example.com:9443",
        wireguard_interface="wg-test",
        wireguard_endpoint_host="vpn.example.com",
        wireguard_endpoint_port=45184,
        state_dir=str(tmp_path),
    )

    assert response["ok"] is True
    assert _config_path(tmp_path).exists()

    config = get_client_config(state_dir=str(tmp_path))
    assert config["data"]["server"]["manager_host"] == "example.com"
    assert config["data"]["server"]["registry"] == "registry.example.com:5000"
    assert config["data"]["wireguard"]["interface"] == "wg-test"


def test_prepare_wireguard_profile_writes_expected_config(tmp_path: Path) -> None:
    configure_environment(state_dir=str(tmp_path), wireguard_interface="wg-seller")

    response = prepare_wireguard_profile(
        server_public_key="server-public",
        client_private_key="client-private",
        client_address="10.88.0.2/32",
        endpoint_host="vpn.example.com",
        endpoint_port=45184,
        allowed_ips="10.88.0.0/24",
        interface_name="wg-seller",
        state_dir=str(tmp_path),
    )

    config_path = _wireguard_config_path("wg-seller", tmp_path)
    assert response["ok"] is True
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "PrivateKey = client-private" in content
    assert "Endpoint = vpn.example.com:45184" in content
    assert "AllowedIPs = 10.88.0.0/24" in content


def test_build_remote_image_ref_uses_registry_and_repository() -> None:
    remote_ref = _build_remote_image_ref(
        repository="seller/demo",
        remote_tag="v1",
        registry="81.70.52.75:5000",
    )

    assert remote_ref == "81.70.52.75:5000/seller/demo:v1"


def test_explain_seller_intent_extracts_share_percent() -> None:
    response = explain_seller_intent("我能把自己电脑性能的10%上传到平台获取收益吗")

    assert response["ok"] is True
    assert response["share_percent_preference"] == 10
    assert "10%" in response["explanation"]


def test_fetch_codex_runtime_bootstrap_masks_secret_and_updates_config(tmp_path: Path, monkeypatch) -> None:
    configure_environment(state_dir=str(tmp_path), backend_url="http://127.0.0.1:8000")
    config = get_client_config(mask_secrets=False, state_dir=str(tmp_path))["data"]
    config["auth"]["access_token"] = "access-token"
    _config_path(tmp_path).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        "seller_client.agent_mcp._run_backend_request",
        lambda *args, **kwargs: {
            "ok": True,
            "body": json.dumps(
                {
                    "model_provider": "OpenAI",
                    "model": "gpt-5.4",
                    "review_model": "gpt-5.4",
                    "model_reasoning_effort": "xhigh",
                    "disable_response_storage": True,
                    "network_access": "enabled",
                    "windows_wsl_setup_acknowledged": True,
                    "model_context_window": 1000000,
                    "model_auto_compact_token_limit": 900000,
                    "provider": {
                        "name": "OpenAI",
                        "base_url": "https://xlabapi.top/v1",
                        "wire_api": "responses",
                        "requires_openai_auth": True,
                    },
                    "auth": {"OPENAI_API_KEY": "sk-secret-12345678"},
                    "auth_source": "env:OPENAI_API_KEY",
                }
            ),
        },
    )

    response = fetch_codex_runtime_bootstrap(state_dir=str(tmp_path))

    assert response["ok"] is True
    assert response["data"]["auth"]["OPENAI_API_KEY"].startswith("sk-s")
    updated = get_client_config(mask_secrets=False, state_dir=str(tmp_path))["data"]
    assert updated["runtime"]["codex_runtime_ready"] is True
    assert updated["runtime"]["codex_model"] == "gpt-5.4"


def test_bootstrap_wireguard_from_platform_prepares_profile(tmp_path: Path, monkeypatch) -> None:
    configure_environment(state_dir=str(tmp_path), backend_url="http://127.0.0.1:8000", wireguard_interface="wg-seller")
    config = get_client_config(mask_secrets=False, state_dir=str(tmp_path))["data"]
    config["auth"]["node_registration_token"] = "node-token"
    config["auth"]["device_fingerprint"] = "device-001"
    _config_path(tmp_path).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        "seller_client.agent_mcp.generate_wireguard_keypair",
        lambda: {"ok": True, "private_key": "client-private", "public_key": "client-public", "wg_bin": "wg"},
    )
    monkeypatch.setattr(
        "seller_client.agent_mcp.request_wireguard_bootstrap",
        lambda client_public_key, backend_url=None, state_dir=None: {
            "ok": True,
            "data": {
                "server_public_key": "server-public",
                "client_address": "10.88.0.20/32",
                "server_endpoint_host": "81.70.52.75",
                "server_endpoint_port": 51820,
                "allowed_ips": "10.88.0.0/16",
                "interface_name": "wg-seller",
                "dns": "",
                "persistent_keepalive": 25,
                "activation_mode": "server_peer_applied",
                "server_peer_apply_required": False,
            },
        },
    )
    monkeypatch.setattr(
        "seller_client.agent_mcp.connect_server_vpn",
        lambda interface_name="wg-seller", state_dir=None: {"ok": True, "action": "connected"},
    )

    response = bootstrap_wireguard_from_platform(state_dir=str(tmp_path))

    assert response["ok"] is True
    assert response["profile_result"]["ok"] is True
    assert response["activation_result"]["ok"] is True
    content = _wireguard_config_path("wg-seller", tmp_path).read_text(encoding="utf-8")
    assert "PublicKey = server-public" in content
    updated = get_client_config(mask_secrets=False, state_dir=str(tmp_path))["data"]
    assert updated["runtime"]["wireguard_profile_status"] == "active"
    assert updated["wireguard"]["client_public_key"] == "client-public"


def test_fetch_swarm_worker_join_token_updates_config(tmp_path: Path, monkeypatch) -> None:
    configure_environment(state_dir=str(tmp_path), backend_url="http://127.0.0.1:8000")
    config = get_client_config(mask_secrets=False, state_dir=str(tmp_path))["data"]
    config["auth"]["access_token"] = "access-token"
    _config_path(tmp_path).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        "seller_client.agent_mcp._run_backend_request",
        lambda *args, **kwargs: {
            "ok": True,
            "body": json.dumps(
                {
                    "join_token": "SWMTKN-test",
                    "manager_host": "81.70.52.75",
                    "manager_port": 2377,
                }
            ),
        },
    )

    response = fetch_swarm_worker_join_token(state_dir=str(tmp_path))

    assert response["ok"] is True
    updated = get_client_config(mask_secrets=False, state_dir=str(tmp_path))["data"]
    assert updated["server"]["manager_host"] == "81.70.52.75"
    assert updated["server"]["manager_port"] == 2377


def test_ensure_joined_to_platform_swarm_noops_when_already_active(monkeypatch) -> None:
    monkeypatch.setattr(
        "seller_client.agent_mcp.swarm_summary",
        lambda: {"info": {"ok": True, "stdout": "state=active node_id=node-1 control=false"}},
    )

    response = ensure_joined_to_platform_swarm()

    assert response["ok"] is True
    assert response["action"] == "already_joined"


def test_connect_server_vpn_uses_elevated_helper_on_access_denied(tmp_path: Path, monkeypatch) -> None:
    configure_environment(state_dir=str(tmp_path), wireguard_interface="wg-seller")
    prepare_wireguard_profile(
        server_public_key="server-public",
        client_private_key="client-private",
        client_address="10.66.66.10/32",
        endpoint_host="81.70.52.75",
        endpoint_port=45182,
        allowed_ips="10.66.66.0/24",
        interface_name="wg-seller",
        state_dir=str(tmp_path),
    )

    monkeypatch.setattr("seller_client.agent_mcp.platform.system", lambda: "Windows")
    monkeypatch.setattr("seller_client.agent_mcp.windows_is_elevated", lambda: False)
    monkeypatch.setattr("seller_client.agent_mcp._windows_wireguard_helper_installed", lambda: True)
    monkeypatch.setattr("seller_client.agent_mcp._wireguard_windows_exe", lambda: "C:\\Program Files\\WireGuard\\wireguard.exe")
    monkeypatch.setattr(
        "seller_client.agent_mcp._run_windows_wireguard_helper",
        lambda **kwargs: {"ok": True, "helper_result": {"ok": True, "request_id": "req-1"}},
    )

    response = connect_server_vpn(state_dir=str(tmp_path))

    assert response["ok"] is True
    assert response["mode"] == "elevated_helper"
