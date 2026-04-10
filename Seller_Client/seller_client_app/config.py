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


def _env_optional_str(name: str, default: str | None) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return default
    cleaned = raw.strip()
    return cleaned or None


@dataclass(frozen=True, slots=True)
class Settings:
    app_host: str = "127.0.0.1"
    app_port: int = 8901
    backend_base_url: str = "https://pivotcompute.store"
    backend_api_prefix: str = "/api/v1"
    windows_workspace_root: str = r"D:\AI\Pivot_Client\seller_client"
    non_windows_workspace_root: str = "/tmp/pivot_seller_client"
    session_subdir_name: str = "sessions"
    logs_subdir_name: str = "logs"
    workspace_subdir_name: str = "workspace"
    health_subdir_name: str = "health"
    exports_subdir_name: str = "exports"
    codex_command: str = "codex"
    codex_mcp_server_name_prefix: str = "seller-client-tools"
    codex_exec_timeout_seconds: int = 180
    codex_exec_sandbox: str = "read-only"
    codex_config_template_path: Path = Path(__file__).resolve().parents[2] / "env_setup_and_install" / "codex.config.toml"
    codex_auth_source_path: Path = Path.home() / ".codex" / "auth.json"
    window_session_ttl_seconds: int = 90
    window_session_heartbeat_interval_seconds: int = 15
    heartbeat_interval_seconds: int = 30
    windows_deploy_root: str = r"D:\AI\Pivot_Client\seller_client"
    windows_ssh_host_alias: str = "win-local-via-wg"
    windows_wireguard_tunnel_name: str = "wg-seller"
    windows_ubuntu_distro: str = "Ubuntu"
    manager_wireguard_address: str = "10.66.66.1"
    manager_public_address: str = "81.70.52.75"
    manager_ssh_port: int = 22
    default_tcp_validation_port: int = 8080
    default_expected_wireguard_ip: str | None = "10.66.66.10"
    external_api_token: str | None = None
    supported_accelerators_csv: str = "gpu,cpu"
    supported_offer_tiers_csv: str = "small,medium,large"

    @property
    def workspace_root(self) -> str:
        if platform.system() == "Windows":
            return self.windows_workspace_root
        return self.non_windows_workspace_root

    @property
    def workspace_root_path(self) -> Path:
        return Path(self.workspace_root)

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @property
    def health_root_path(self) -> Path:
        return self.workspace_root_path / self.health_subdir_name

    @property
    def exports_root_path(self) -> Path:
        return self.workspace_root_path / self.exports_subdir_name

    @property
    def wireguard_runtime_cache_dir_path(self) -> Path:
        return self.project_root / ".cache" / "seller-zero-flow" / "wireguard"

    @property
    def wireguard_runtime_config_path(self) -> Path:
        return self.wireguard_runtime_cache_dir_path / f"{self.windows_wireguard_tunnel_name}.conf"

    @property
    def supported_accelerators(self) -> tuple[str, ...]:
        return _csv_values(self.supported_accelerators_csv)

    @property
    def supported_offer_tiers(self) -> tuple[str, ...]:
        return _csv_values(self.supported_offer_tiers_csv)

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            app_host=os.getenv("SELLER_CLIENT_APP_HOST", defaults.app_host),
            app_port=_env_int("SELLER_CLIENT_APP_PORT", defaults.app_port),
            backend_base_url=os.getenv("SELLER_CLIENT_BACKEND_BASE_URL", defaults.backend_base_url),
            backend_api_prefix=os.getenv("SELLER_CLIENT_BACKEND_API_PREFIX", defaults.backend_api_prefix),
            windows_workspace_root=os.getenv("SELLER_CLIENT_WINDOWS_WORKSPACE_ROOT", defaults.windows_workspace_root),
            non_windows_workspace_root=os.getenv(
                "SELLER_CLIENT_NON_WINDOWS_WORKSPACE_ROOT",
                defaults.non_windows_workspace_root,
            ),
            session_subdir_name=os.getenv("SELLER_CLIENT_SESSION_SUBDIR_NAME", defaults.session_subdir_name),
            logs_subdir_name=os.getenv("SELLER_CLIENT_LOGS_SUBDIR_NAME", defaults.logs_subdir_name),
            workspace_subdir_name=os.getenv("SELLER_CLIENT_WORKSPACE_SUBDIR_NAME", defaults.workspace_subdir_name),
            health_subdir_name=os.getenv("SELLER_CLIENT_HEALTH_SUBDIR_NAME", defaults.health_subdir_name),
            exports_subdir_name=os.getenv("SELLER_CLIENT_EXPORTS_SUBDIR_NAME", defaults.exports_subdir_name),
            codex_command=os.getenv("SELLER_CLIENT_CODEX_COMMAND", defaults.codex_command),
            codex_mcp_server_name_prefix=os.getenv(
                "SELLER_CLIENT_CODEX_MCP_SERVER_NAME_PREFIX",
                defaults.codex_mcp_server_name_prefix,
            ),
            codex_exec_timeout_seconds=_env_int(
                "SELLER_CLIENT_CODEX_EXEC_TIMEOUT_SECONDS",
                defaults.codex_exec_timeout_seconds,
            ),
            codex_exec_sandbox=os.getenv("SELLER_CLIENT_CODEX_EXEC_SANDBOX", defaults.codex_exec_sandbox),
            codex_config_template_path=Path(
                os.getenv("SELLER_CLIENT_CODEX_CONFIG_TEMPLATE_PATH", str(defaults.codex_config_template_path))
            ).expanduser(),
            codex_auth_source_path=Path(
                os.getenv("SELLER_CLIENT_CODEX_AUTH_SOURCE_PATH", str(defaults.codex_auth_source_path))
            ).expanduser(),
            window_session_ttl_seconds=_env_int(
                "SELLER_CLIENT_WINDOW_SESSION_TTL_SECONDS",
                defaults.window_session_ttl_seconds,
            ),
            window_session_heartbeat_interval_seconds=_env_int(
                "SELLER_CLIENT_WINDOW_SESSION_HEARTBEAT_INTERVAL_SECONDS",
                defaults.window_session_heartbeat_interval_seconds,
            ),
            heartbeat_interval_seconds=_env_int(
                "SELLER_CLIENT_HEARTBEAT_INTERVAL_SECONDS",
                defaults.heartbeat_interval_seconds,
            ),
            windows_deploy_root=os.getenv("SELLER_CLIENT_WINDOWS_DEPLOY_ROOT", defaults.windows_deploy_root),
            windows_ssh_host_alias=os.getenv("SELLER_CLIENT_WINDOWS_SSH_HOST_ALIAS", defaults.windows_ssh_host_alias),
            windows_wireguard_tunnel_name=os.getenv(
                "SELLER_CLIENT_WINDOWS_WIREGUARD_TUNNEL_NAME",
                defaults.windows_wireguard_tunnel_name,
            ),
            windows_ubuntu_distro=os.getenv("SELLER_CLIENT_WINDOWS_UBUNTU_DISTRO", defaults.windows_ubuntu_distro),
            manager_wireguard_address=os.getenv(
                "SELLER_CLIENT_MANAGER_WIREGUARD_ADDRESS",
                defaults.manager_wireguard_address,
            ),
            manager_public_address=os.getenv(
                "SELLER_CLIENT_MANAGER_PUBLIC_ADDRESS",
                defaults.manager_public_address,
            ),
            manager_ssh_port=_env_int("SELLER_CLIENT_MANAGER_SSH_PORT", defaults.manager_ssh_port),
            default_tcp_validation_port=_env_int(
                "SELLER_CLIENT_DEFAULT_TCP_VALIDATION_PORT",
                defaults.default_tcp_validation_port,
            ),
            default_expected_wireguard_ip=_env_optional_str(
                "SELLER_CLIENT_DEFAULT_EXPECTED_WIREGUARD_IP",
                defaults.default_expected_wireguard_ip,
            ),
            external_api_token=os.getenv("SELLER_CLIENT_EXTERNAL_API_TOKEN", defaults.external_api_token),
            supported_accelerators_csv=os.getenv(
                "SELLER_CLIENT_SUPPORTED_ACCELERATORS",
                defaults.supported_accelerators_csv,
            ),
            supported_offer_tiers_csv=os.getenv(
                "SELLER_CLIENT_SUPPORTED_OFFER_TIERS",
                defaults.supported_offer_tiers_csv,
            ),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


def _csv_values(raw: str) -> tuple[str, ...]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(values)
