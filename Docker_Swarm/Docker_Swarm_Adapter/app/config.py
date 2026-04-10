from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    adapter_host: str
    adapter_port: int
    adapter_token: str
    swarm_manager_addr: str
    swarm_control_addr: str
    registry_host: str
    registry_port: int
    wireguard_interface: str
    wireguard_config_path: Path
    portainer_url: str | None
    log_level: str
    command_timeout_seconds: int
    runtime_base_image_prefix: str
    runtime_base_image_label: str
    runtime_contract_version: str
    runtime_contract_version_label: str
    runtime_buyer_agent_label: str
    runtime_buyer_agent_version: str
    runtime_shell_agent_path: str
    runtime_shell_agent_port: int
    runtime_workspace_root: str
    runtime_shell_embed_path: str
    runtime_workspace_upload_path: str
    runtime_workspace_extract_path: str
    runtime_workspace_status_path: str
    gateway_image: str
    gateway_target_port: int
    gateway_access_scheme: str
    gateway_published_port_start: int
    gateway_published_port_end: int
    session_network_prefix: str
    wireguard_client_ip_range_start: int
    wireguard_client_ip_range_end: int
    adapter_name: str = "swarm-adapter"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        adapter_host=os.getenv("ADAPTER_HOST", "0.0.0.0"),
        adapter_port=_env_int("ADAPTER_PORT", 8010),
        adapter_token=os.getenv("ADAPTER_TOKEN", ""),
        swarm_manager_addr=os.getenv("SWARM_MANAGER_ADDR", "81.70.52.75"),
        swarm_control_addr=os.getenv("SWARM_CONTROL_ADDR") or os.getenv("SWARM_MANAGER_ADDR", "81.70.52.75"),
        registry_host=os.getenv("REGISTRY_HOST", "pivotcompute.store"),
        registry_port=_env_int("REGISTRY_PORT", 5000),
        wireguard_interface=os.getenv("WIREGUARD_INTERFACE", "wg0"),
        wireguard_config_path=Path(os.getenv("WIREGUARD_CONFIG_PATH", "/etc/wireguard/wg0.conf")),
        portainer_url=os.getenv("PORTAINER_URL") or None,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        command_timeout_seconds=_env_int("COMMAND_TIMEOUT_SECONDS", 30),
        runtime_base_image_prefix=os.getenv("RUNTIME_BASE_IMAGE_PREFIX", "pivotcompute/runtime-base"),
        runtime_base_image_label=os.getenv("RUNTIME_BASE_IMAGE_LABEL", "io.pivot.runtime.base_image"),
        runtime_contract_version=os.getenv("RUNTIME_CONTRACT_VERSION", "v1"),
        runtime_contract_version_label=os.getenv(
            "RUNTIME_CONTRACT_VERSION_LABEL", "io.pivot.runtime.contract_version"
        ),
        runtime_buyer_agent_label=os.getenv("RUNTIME_BUYER_AGENT_LABEL", "io.pivot.runtime.buyer_agent"),
        runtime_buyer_agent_version=os.getenv("RUNTIME_BUYER_AGENT_VERSION", "v1"),
        runtime_shell_agent_path=os.getenv("RUNTIME_SHELL_AGENT_PATH", "/usr/local/bin/pivot-shell-agent"),
        runtime_shell_agent_port=_env_int("RUNTIME_SHELL_AGENT_PORT", 7681),
        runtime_workspace_root=os.getenv("RUNTIME_WORKSPACE_ROOT", "/workspace"),
        runtime_shell_embed_path=os.getenv("RUNTIME_SHELL_EMBED_PATH", "/shell/"),
        runtime_workspace_upload_path=os.getenv("RUNTIME_WORKSPACE_UPLOAD_PATH", "/api/workspace/upload"),
        runtime_workspace_extract_path=os.getenv("RUNTIME_WORKSPACE_EXTRACT_PATH", "/api/workspace/extract"),
        runtime_workspace_status_path=os.getenv("RUNTIME_WORKSPACE_STATUS_PATH", "/api/workspace/status"),
        gateway_image=os.getenv("GATEWAY_IMAGE", "caddy:2-alpine"),
        gateway_target_port=_env_int("GATEWAY_TARGET_PORT", 8080),
        gateway_access_scheme=os.getenv("GATEWAY_ACCESS_SCHEME", "http"),
        gateway_published_port_start=_env_int("GATEWAY_PUBLISHED_PORT_START", 32080),
        gateway_published_port_end=_env_int("GATEWAY_PUBLISHED_PORT_END", 32199),
        session_network_prefix=os.getenv("SESSION_NETWORK_PREFIX", "pivot-session"),
        wireguard_client_ip_range_start=_env_int("WIREGUARD_CLIENT_IP_RANGE_START", 200),
        wireguard_client_ip_range_end=_env_int("WIREGUARD_CLIENT_IP_RANGE_END", 250),
    )
