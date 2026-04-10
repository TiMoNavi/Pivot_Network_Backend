from __future__ import annotations

import platform
from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SELLER_CLIENT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8901
    backend_base_url: str = "https://pivotcompute.store"
    backend_api_prefix: str = "/api/v1"

    windows_workspace_root: str = r"D:\AI\Pivot_Client\seller_client"
    non_windows_workspace_root: str = "/tmp/pivot_seller_client"
    session_subdir_name: str = "sessions"
    logs_subdir_name: str = "logs"
    workspace_subdir_name: str = "workspace"
    ubuntu_distribution_name: str = "Ubuntu"
    ubuntu_runtime_root: str = "/opt/pivot/compute"
    ubuntu_workspace_root: str = "/opt/pivot/workspace"
    ubuntu_logs_root: str = "/opt/pivot/logs"
    ubuntu_compute_interface_name: str = "wg-compute"
    ubuntu_compute_address: str = "10.66.66.11/32"
    ubuntu_swarm_advertise_addr: str = "10.66.66.11"
    ubuntu_swarm_data_path_addr: str = "10.66.66.11"
    ubuntu_required_packages: tuple[str, ...] = ("docker.io", "wireguard-tools", "iproute2", "iptables")

    server_public_host: str = "81.70.52.75"
    server_public_ssh_port: int = 22
    server_wireguard_ip: str = "10.66.66.1"
    server_wireguard_ssh_port: int = 22
    server_wireguard_endpoint_port: int = 45182
    wireguard_interface_name: str = "wg-seller"
    gpu_smoke_image: str = "nvidia/cuda:12.3.2-base-ubuntu22.04"

    codex_command: str = "codex"
    codex_mcp_server_name: str = "seller-client-tools"
    codex_exec_timeout_seconds: int = 180
    heartbeat_interval_seconds: int = 30
    window_session_ttl_seconds: int = 90
    window_session_heartbeat_interval_seconds: int = 15
    windows_host_script_timeout_seconds: int = 900
    standard_image_pull_timeout_seconds: int = 1800
    standard_image_verify_timeout_seconds: int = 1800

    @computed_field
    @property
    def workspace_root(self) -> str:
        if platform.system() == "Windows":
            return self.windows_workspace_root
        return self.non_windows_workspace_root

    @computed_field
    @property
    def workspace_root_path(self) -> Path:
        return Path(self.workspace_root)


@lru_cache
def get_settings() -> Settings:
    return Settings()
