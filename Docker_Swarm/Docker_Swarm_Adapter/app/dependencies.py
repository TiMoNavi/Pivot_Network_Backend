from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.drivers.command import CommandRunner
from app.drivers.docker import DockerDriver
from app.drivers.wireguard import WireGuardDriver
from app.services.health_service import HealthService
from app.services.swarm_nodes import SwarmNodeService
from app.services.swarm_runtime import SwarmRuntimeService
from app.services.wireguard import WireGuardService


@lru_cache
def get_command_runner() -> CommandRunner:
    settings = get_settings()
    return CommandRunner(timeout_seconds=settings.command_timeout_seconds)


@lru_cache
def get_docker_driver() -> DockerDriver:
    return DockerDriver(runner=get_command_runner())


@lru_cache
def get_wireguard_driver() -> WireGuardDriver:
    settings = get_settings()
    return WireGuardDriver(
        runner=get_command_runner(),
        interface=settings.wireguard_interface,
        config_path=settings.wireguard_config_path,
    )


@lru_cache
def get_health_service() -> HealthService:
    return HealthService(
        settings=get_settings(),
        docker=get_docker_driver(),
        wireguard=get_wireguard_driver(),
    )


@lru_cache
def get_swarm_node_service() -> SwarmNodeService:
    return SwarmNodeService(
        settings=get_settings(),
        docker=get_docker_driver(),
    )


@lru_cache
def get_runtime_service() -> SwarmRuntimeService:
    return SwarmRuntimeService(
        settings=get_settings(),
        docker=get_docker_driver(),
        swarm_nodes=get_swarm_node_service(),
        wireguard=get_wireguard_driver(),
        wireguard_service=get_wireguard_service(),
    )


@lru_cache
def get_wireguard_service() -> WireGuardService:
    return WireGuardService(
        settings=get_settings(),
        wireguard=get_wireguard_driver(),
    )
