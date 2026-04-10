from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer.") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    app_host: str = "127.0.0.1"
    app_port: int = 8902
    backend_base_url: str = "https://pivotcompute.store"
    backend_api_prefix: str = "/api/v1"
    windows_workspace_root: str = r"D:\AI\Pivot_Client\buyer_client"
    non_windows_workspace_root: str = "/tmp/pivot_buyer_client"
    session_subdir_name: str = "sessions"
    logs_subdir_name: str = "logs"
    workspace_subdir_name: str = "workspace"
    window_session_ttl_seconds: int = 90
    heartbeat_interval_seconds: int = 30
    default_requested_duration_minutes: int = 60

    @property
    def workspace_root(self) -> str:
        if platform.system() == "Windows":
            return self.windows_workspace_root
        return self.non_windows_workspace_root

    @property
    def workspace_root_path(self) -> Path:
        return Path(self.workspace_root)

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            app_host=os.getenv("BUYER_CLIENT_APP_HOST", defaults.app_host),
            app_port=_env_int("BUYER_CLIENT_APP_PORT", defaults.app_port),
            backend_base_url=os.getenv("BUYER_CLIENT_BACKEND_BASE_URL", defaults.backend_base_url),
            backend_api_prefix=os.getenv("BUYER_CLIENT_BACKEND_API_PREFIX", defaults.backend_api_prefix),
            windows_workspace_root=os.getenv("BUYER_CLIENT_WINDOWS_WORKSPACE_ROOT", defaults.windows_workspace_root),
            non_windows_workspace_root=os.getenv(
                "BUYER_CLIENT_NON_WINDOWS_WORKSPACE_ROOT",
                defaults.non_windows_workspace_root,
            ),
            session_subdir_name=os.getenv("BUYER_CLIENT_SESSION_SUBDIR_NAME", defaults.session_subdir_name),
            logs_subdir_name=os.getenv("BUYER_CLIENT_LOGS_SUBDIR_NAME", defaults.logs_subdir_name),
            workspace_subdir_name=os.getenv("BUYER_CLIENT_WORKSPACE_SUBDIR_NAME", defaults.workspace_subdir_name),
            window_session_ttl_seconds=_env_int(
                "BUYER_CLIENT_WINDOW_SESSION_TTL_SECONDS",
                defaults.window_session_ttl_seconds,
            ),
            heartbeat_interval_seconds=_env_int(
                "BUYER_CLIENT_HEARTBEAT_INTERVAL_SECONDS",
                defaults.heartbeat_interval_seconds,
            ),
            default_requested_duration_minutes=_env_int(
                "BUYER_CLIENT_DEFAULT_REQUESTED_DURATION_MINUTES",
                defaults.default_requested_duration_minutes,
            ),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
