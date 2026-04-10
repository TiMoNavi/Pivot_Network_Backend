from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="BACKEND_",
    )

    project_name: str = "Pivot Platform Backend"
    project_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    postgres_user: str = "pivot"
    postgres_password: str = "pivot"
    postgres_db: str = "pivot_backend"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str | None = None

    adapter_base_url: str = "http://localhost:8010"
    adapter_token: str = "change-me"
    adapter_timeout_seconds: float = 60.0
    session_token_ttl_hours: int = 24
    enable_builtin_workers: bool = False
    runtime_refresh_stale_after_minutes: int = 2
    runtime_refresh_interval_seconds: int = 120
    runtime_reaper_interval_seconds: int = 120
    access_code_reaper_interval_seconds: int = 300
    maintenance_batch_limit: int = 25

    managed_runtime_base_image: str = "pivotcompute/runtime-base:ubuntu-22.04"
    managed_runtime_contract_version: str = "v1"
    managed_runtime_shell_agent_path: str = "/usr/local/bin/pivot-shell-agent"
    seller_swarm_standard_image_ref: str = "pivotcompute/seller-swarm-standard:ubuntu-22.04-cuda12.3"
    seller_swarm_standard_image_description: str = (
        "Standard seller swarm image with CUDA, Python, WireGuard, Docker CLI, and swarm helper utilities."
    )
    seller_allowed_registry_host: str = "pivotcompute.store"
    seller_allowed_registry_namespace: str = "pivotcompute"
    seller_onboarding_session_ttl_minutes: int = 60

    seller_codex_model_provider: str = "OpenAI"
    seller_codex_model: str = "gpt-5.4"
    seller_codex_review_model: str = "gpt-5.4"
    seller_codex_model_reasoning_effort: str = "xhigh"
    seller_codex_disable_response_storage: bool = True
    seller_codex_network_access: str = "enabled"
    seller_codex_windows_wsl_setup_acknowledged: bool = True
    seller_codex_model_context_window: int = 1_000_000
    seller_codex_model_auto_compact_token_limit: int = 900_000
    seller_codex_base_url: str = "https://xlabapi.top/v1"
    seller_codex_wire_api: str = "responses"
    seller_codex_requires_openai_auth: bool = True
    seller_codex_openai_api_key: str | None = None
    seller_codex_mcp_server_name: str = "seller-client-tools"
    seller_codex_window_session_scope: str = "browser_window"
    seller_compute_substrate: str = "wsl_ubuntu"
    seller_compute_host_type: str = "windows_wsl_ubuntu"
    seller_compute_network_mode: str = "wireguard"
    seller_compute_runtime: str = "docker_engine"
    seller_compute_ubuntu_distribution_name: str = "Ubuntu"
    seller_compute_ubuntu_workspace_root: str = "/opt/pivot/workspace"
    seller_compute_ubuntu_runtime_root: str = "/opt/pivot/compute"
    seller_compute_ubuntu_logs_root: str = "/opt/pivot/logs"
    seller_compute_docker_engine_install_mode: str = "apt"
    seller_compute_required_packages_csv: str = "docker.io,wireguard-tools,iproute2,iptables"
    seller_compute_wireguard_interface_name: str = "wg-compute"
    seller_compute_wireguard_client_ip: str = "10.66.66.11/32"
    seller_compute_wireguard_server_public_key: str = "puGAoUTF0vyha+32vxQ+BBVOWXlCOUzhFoNe5tJ9hyo="
    seller_compute_wireguard_endpoint: str = "81.70.52.75:45182"
    seller_compute_wireguard_allowed_ips_csv: str = "10.66.66.0/24"
    seller_compute_wireguard_persistent_keepalive: int = 25
    seller_compute_swarm_advertise_addr: str = "10.66.66.11"
    seller_compute_swarm_data_path_addr: str = "10.66.66.11"

    buyer_runtime_client_session_ttl_minutes: int = 60
    buyer_workspace_sync_max_mb: int = 512
    buyer_runtime_workspace_root: str = "/workspace"
    buyer_shell_embed_path: str = "/shell/"
    buyer_workspace_upload_path: str = "/api/workspace/upload"
    buyer_workspace_extract_path: str = "/api/workspace/extract"
    buyer_workspace_status_path: str = "/api/workspace/status"

    buyer_codex_model_provider: str = "OpenAI"
    buyer_codex_model: str = "gpt-5.4"
    buyer_codex_review_model: str = "gpt-5.4"
    buyer_codex_model_reasoning_effort: str = "xhigh"
    buyer_codex_disable_response_storage: bool = True
    buyer_codex_network_access: str = "enabled"
    buyer_codex_windows_wsl_setup_acknowledged: bool = True
    buyer_codex_model_context_window: int = 1_000_000
    buyer_codex_model_auto_compact_token_limit: int = 900_000
    buyer_codex_base_url: str = "https://xlabapi.top/v1"
    buyer_codex_wire_api: str = "responses"
    buyer_codex_requires_openai_auth: bool = True
    buyer_codex_openai_api_key: str | None = None
    buyer_codex_mcp_server_name: str = "buyer-client-tools"

    @computed_field
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url

        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
