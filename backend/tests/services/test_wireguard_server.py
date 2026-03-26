from app.core.config import settings
from app.services.wireguard_server import apply_server_peer


class _FakeClient:
    def close(self) -> None:
        return None


def test_apply_server_peer_removes_conflicting_allowed_ips_peer(monkeypatch) -> None:
    commands: list[str] = []

    monkeypatch.setattr("app.services.wireguard_server._ssh_client", lambda settings: _FakeClient())

    def fake_exec(client, command: str) -> dict[str, object]:
        commands.append(command)
        if "python3 - <<'PY'" in command:
            return {
                "command": command,
                "stdout": '{"changed": true, "path": "/etc/wireguard/wg0.conf", "removed_public_keys": ["stale-peer-key"]}',
                "stderr": "",
                "ok": True,
            }
        if "peer 'stale-peer-key' remove" in command:
            return {"command": command, "stdout": "", "stderr": "", "ok": True}
        if "peer 'current-peer-key' allowed-ips '10.66.66.10/32'" in command:
            return {"command": command, "stdout": "", "stderr": "", "ok": True}
        if command == f"wg show {settings.WIREGUARD_SERVER_INTERFACE}":
            return {"command": command, "stdout": "interface: wg0", "stderr": "", "ok": True}
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("app.services.wireguard_server._exec", fake_exec)

    result = apply_server_peer(
        settings,
        public_key="current-peer-key",
        client_address="10.66.66.10/32",
        persistent_keepalive=25,
    )

    assert result["ok"] is True
    assert len(result["removed_runtime_peers"]) == 1
    stale_index = next(i for i, command in enumerate(commands) if "peer 'stale-peer-key' remove" in command)
    current_index = next(
        i for i, command in enumerate(commands) if "peer 'current-peer-key' allowed-ips '10.66.66.10/32'" in command
    )
    assert stale_index < current_index
