from __future__ import annotations

from app.config import Settings
from app.drivers.command import CommandExecutionError
from app.drivers.docker import DockerDriver
from app.drivers.wireguard import WireGuardDriver
from app.schemas.health import HealthResponse


class HealthService:
    def __init__(self, settings: Settings, docker: DockerDriver, wireguard: WireGuardDriver) -> None:
        self.settings = settings
        self.docker = docker
        self.wireguard = wireguard

    def get_health(self) -> HealthResponse:
        docker_cli = False
        swarm_state = "unknown"
        wireguard_readable = False

        try:
            swarm_info = self.docker.info()
            docker_cli = True
            swarm_state = str(swarm_info.get("LocalNodeState") or "unknown").lower()
        except CommandExecutionError:
            docker_cli = False

        try:
            self.wireguard.read_config()
            wireguard_readable = True
        except OSError:
            wireguard_readable = False

        return HealthResponse(
            status="ok",
            adapter=self.settings.adapter_name,
            docker_cli=docker_cli,
            swarm_state=swarm_state,
            wireguard_readable=wireguard_readable,
        )
