from __future__ import annotations

import platform
from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BUYER_CLIENT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8902
    backend_base_url: str = "https://pivotcompute.store"
    backend_api_prefix: str = "/api/v1"

    windows_workspace_root: str = r"D:\AI\Pivot_Client\buyer_client"
    non_windows_workspace_root: str = "/tmp/pivot_buyer_client"
    session_subdir_name: str = "sessions"
    logs_subdir_name: str = "logs"
    workspace_subdir_name: str = "workspace"

    server_public_host: str = "pivotcompute.store"
    server_public_ssh_port: int = 22
    wireguard_tunnel_prefix: str = "pivot-buyer"
    default_network_mode: str = "wireguard"

    codex_command: str = "codex"
    codex_mcp_server_name: str = "buyer-client-tools"
    codex_exec_timeout_seconds: int = 180
    heartbeat_interval_seconds: int = 30
    workspace_archive_name: str = "workspace.zip"

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
