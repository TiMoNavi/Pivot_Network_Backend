import subprocess

import pytest

from app.core.config import settings
from app.services.swarm_adapter import (
    SWARM_INFO_FORMAT,
    SwarmAdapterUnavailableError,
    get_swarm_health,
)


def test_get_swarm_health_returns_parsed_swarm_state(monkeypatch) -> None:
    expected_command = [
        settings.SWARM_DOCKER_BIN,
        "info",
        "--format",
        SWARM_INFO_FORMAT,
    ]

    monkeypatch.setattr("app.services.swarm_adapter.shutil.which", lambda _: "docker")

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess:
        assert command == expected_command
        assert capture_output is True
        assert text is True
        assert check is True
        assert timeout == settings.SWARM_DOCKER_TIMEOUT_SECONDS
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"LocalNodeState":"active","NodeID":"node-1",'
                '"NodeAddr":"192.168.65.3","ControlAvailable":true,"Error":""}'
            ),
            stderr="",
        )

    monkeypatch.setattr("app.services.swarm_adapter.subprocess.run", fake_run)

    assert get_swarm_health() == {
        "status": "ok",
        "adapter": "docker-cli",
        "reachable": True,
        "swarm": {
            "state": "active",
            "node_id": "node-1",
            "node_addr": "192.168.65.3",
            "control_available": True,
            "error": None,
        },
    }


def test_get_swarm_health_raises_when_docker_is_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.services.swarm_adapter.shutil.which", lambda _: None)

    with pytest.raises(
        SwarmAdapterUnavailableError,
        match="Docker CLI 'docker' is not available",
    ):
        get_swarm_health()
