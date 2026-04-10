from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SellerNodeRegisterRequest(BaseModel):
    requested_accelerator: str = "gpu"
    requested_compute_node_id: str | None = None


class RuntimeBaseImageRead(BaseModel):
    image_ref: str
    contract_version: str
    description: str


class RuntimeContractRead(BaseModel):
    contract_version: str
    base_image_prefix: str
    shell_agent_path: str
    requirements: list[str]
    metadata: dict[str, Any] = {}


class SellerBuildPolicyRead(BaseModel):
    allowed_runtime_base_image: str
    runtime_contract_version: str
    shell_agent_path: str
    allowed_registry_host: str
    allowed_registry_namespace: str
    compute_substrate: str
    compute_host_type: str
    compute_network_mode: str
    compute_runtime: str
    dockerfile_rules: list[str]
    allowed_resource_fields: list[str]
    gpu_support_required: bool


class SellerWindowsHostBootstrapRead(BaseModel):
    workspace_root: str
    codex_mcp_server_name: str
    start_command: str
    seller_console_url: str


class SellerSwarmStandardImageBootstrapRead(BaseModel):
    image_ref: str
    description: str
    pull_command: str
    verify_commands: list[str]


class SellerWireGuardComputePeerRead(BaseModel):
    interface_name: str
    client_ip: str
    server_public_key: str
    endpoint: str
    allowed_ips: list[str]
    persistent_keepalive: int


class SellerSwarmJoinBootstrapRead(BaseModel):
    join_token: str
    manager_addr: str
    manager_port: int
    advertise_addr: str
    data_path_addr: str
    swarm_join_command: str


class SellerUbuntuBootstrapRead(BaseModel):
    distribution_name: str
    required_packages: list[str]
    docker_engine_install_mode: str
    workspace_root: str
    runtime_root: str
    logs_root: str
    wireguard_compute_peer: SellerWireGuardComputePeerRead
    swarm_join: SellerSwarmJoinBootstrapRead
    seller_swarm_standard_image: SellerSwarmStandardImageBootstrapRead
    expected_node_addr: str
    bootstrap_script_bash: str
    bootstrap_script_powershell: str


class SellerOnboardingCreateRequest(BaseModel):
    requested_accelerator: str = "gpu"
    requested_compute_node_id: str | None = None


class SellerOnboardingSessionRead(BaseModel):
    session_id: str
    status: str
    requested_accelerator: str
    requested_compute_node_id: str | None = None
    expires_at: datetime
    last_heartbeat_at: datetime | None = None
    last_env_report: dict[str, Any] | None = None
    last_windows_host_report: dict[str, Any] | None = None
    last_ubuntu_compute_report: dict[str, Any] | None = None
    compute_ready: bool
    policy: SellerBuildPolicyRead


class SellerOnboardingBootstrapConfigRead(BaseModel):
    session_id: str
    expires_at: datetime
    window_session_scope: str
    codex_config_toml: str
    codex_auth_json: str
    mcp_launch: dict[str, Any]
    windows_host_bootstrap: SellerWindowsHostBootstrapRead
    policy: SellerBuildPolicyRead


class SellerUbuntuBootstrapConfigRead(BaseModel):
    session_id: str
    expires_at: datetime
    ubuntu_compute_bootstrap: SellerUbuntuBootstrapRead
    policy: SellerBuildPolicyRead


class SellerOnboardingEnvReportWrite(BaseModel):
    env_report: dict[str, Any]


class SellerComputeReadyWrite(BaseModel):
    detail: dict[str, Any] = {}


class SellerNodeClaimRequest(BaseModel):
    onboarding_session_id: str
    compute_node_id: str
    requested_accelerator: str = "gpu"
