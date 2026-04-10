from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend_app.clients.adapter.client import AdapterClient
from backend_app.core.config import get_settings
from backend_app.repositories.seller_onboarding_repository import SellerOnboardingRepository
from backend_app.schemas.seller import (
    SellerBuildPolicyRead,
    SellerNodeClaimRequest,
    SellerOnboardingBootstrapConfigRead,
    SellerOnboardingCreateRequest,
    SellerOnboardingSessionRead,
    SellerSwarmStandardImageBootstrapRead,
    SellerUbuntuBootstrapConfigRead,
    SellerUbuntuBootstrapRead,
    SellerSwarmJoinBootstrapRead,
    SellerWindowsHostBootstrapRead,
    SellerWireGuardComputePeerRead,
)
from backend_app.services.audit_service import AuditService

ACTIVE_ONBOARDING_STATUSES = {"active", "compute_ready", "claimed"}
TERMINAL_ONBOARDING_STATUSES = {"closed", "expired"}


class SellerOnboardingService:
    def __init__(
        self,
        session: Session,
        adapter_client: AdapterClient,
        audit_service: AuditService | None = None,
    ) -> None:
        self.session = session
        self.adapter_client = adapter_client
        self.repository = SellerOnboardingRepository(session)
        self.audit = audit_service
        self.settings = get_settings()

    def create_session(
        self,
        seller_user_id,
        payload: SellerOnboardingCreateRequest,
    ) -> SellerOnboardingSessionRead:
        now = datetime.now(UTC)
        onboarding_session = self.repository.create(
            seller_user_id=seller_user_id,
            status="active",
            requested_accelerator=payload.requested_accelerator,
            requested_compute_node_id=payload.requested_compute_node_id,
            expires_at=now + timedelta(minutes=self.settings.seller_onboarding_session_ttl_minutes),
            last_heartbeat_at=now,
            last_env_report=None,
        )
        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=seller_user_id,
                actor_role="seller",
                event_type="seller_onboarding_session_created",
                target_type="seller_onboarding_session",
                target_id=str(onboarding_session.id),
                payload={
                    "requested_accelerator": payload.requested_accelerator,
                    "requested_compute_node_id": payload.requested_compute_node_id,
                },
            )
        return self._session_read(onboarding_session)

    def get_session(self, seller_user_id, session_id: str) -> SellerOnboardingSessionRead:
        onboarding_session = self._get_owned_session(seller_user_id, session_id)
        self._expire_if_needed(onboarding_session)
        return self._session_read(onboarding_session)

    def get_bootstrap_config(
        self,
        seller_user_id,
        session_id: str,
    ) -> SellerOnboardingBootstrapConfigRead:
        onboarding_session = self._get_active_session(seller_user_id, session_id)
        api_key = self._resolve_codex_api_key()
        if not api_key:
            raise RuntimeError("Seller onboarding Codex auth is not configured.")

        return SellerOnboardingBootstrapConfigRead(
            session_id=str(onboarding_session.id),
            expires_at=onboarding_session.expires_at,
            window_session_scope=self.settings.seller_codex_window_session_scope,
            codex_config_toml=self._build_codex_config_toml(),
            codex_auth_json=json.dumps(
                {
                    "auth_mode": "openai_api_key",
                    "OPENAI_API_KEY": api_key,
                },
                indent=2,
            ),
            mcp_launch={
                "name": self.settings.seller_codex_mcp_server_name,
                "transport": "stdio",
                "command": ["python", "-m", "seller_client_app.mcp_server"],
            },
            windows_host_bootstrap=self._build_windows_host_bootstrap(),
            policy=self._build_policy(),
        )

    def get_ubuntu_bootstrap(
        self,
        seller_user_id,
        session_id: str,
    ) -> SellerUbuntuBootstrapConfigRead:
        onboarding_session = self._get_active_session(seller_user_id, session_id)
        join_material = self.adapter_client.get_join_material(
            {
                "seller_user_id": str(seller_user_id),
                "requested_accelerator": onboarding_session.requested_accelerator,
                "requested_compute_node_id": onboarding_session.requested_compute_node_id,
            }
        )
        return SellerUbuntuBootstrapConfigRead(
            session_id=str(onboarding_session.id),
            expires_at=onboarding_session.expires_at,
            ubuntu_compute_bootstrap=self._build_ubuntu_bootstrap(
                join_material,
                requested_accelerator=onboarding_session.requested_accelerator,
            ),
            policy=self._build_policy(),
        )

    def update_env_report(self, seller_user_id, session_id: str, env_report: dict[str, Any]) -> SellerOnboardingSessionRead:
        onboarding_session = self._get_active_session(seller_user_id, session_id)
        onboarding_session.last_env_report = env_report
        onboarding_session.last_heartbeat_at = datetime.now(UTC)
        self.repository.save(onboarding_session)
        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=seller_user_id,
                actor_role="seller",
                event_type="seller_onboarding_env_reported",
                target_type="seller_onboarding_session",
                target_id=str(onboarding_session.id),
                payload={"keys": sorted(env_report.keys())},
            )
        return self._session_read(onboarding_session)

    def update_host_env_report(self, seller_user_id, session_id: str, env_report: dict[str, Any]) -> SellerOnboardingSessionRead:
        onboarding_session = self._get_active_session(seller_user_id, session_id)
        payload = dict(onboarding_session.last_env_report or {})
        payload["windows_host"] = env_report
        onboarding_session.last_env_report = payload
        onboarding_session.last_heartbeat_at = datetime.now(UTC)
        self.repository.save(onboarding_session)
        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=seller_user_id,
                actor_role="seller",
                event_type="seller_onboarding_windows_host_reported",
                target_type="seller_onboarding_session",
                target_id=str(onboarding_session.id),
                payload={"keys": sorted(env_report.keys())},
            )
        return self._session_read(onboarding_session)

    def update_ubuntu_env_report(self, seller_user_id, session_id: str, env_report: dict[str, Any]) -> SellerOnboardingSessionRead:
        onboarding_session = self._get_active_session(seller_user_id, session_id)
        payload = dict(onboarding_session.last_env_report or {})
        payload["ubuntu_compute"] = env_report
        onboarding_session.last_env_report = payload
        onboarding_session.last_heartbeat_at = datetime.now(UTC)
        self.repository.save(onboarding_session)
        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=seller_user_id,
                actor_role="seller",
                event_type="seller_onboarding_ubuntu_compute_reported",
                target_type="seller_onboarding_session",
                target_id=str(onboarding_session.id),
                payload={"keys": sorted(env_report.keys())},
            )
        return self._session_read(onboarding_session)

    def mark_compute_ready(self, seller_user_id, session_id: str, detail: dict[str, Any] | None = None) -> SellerOnboardingSessionRead:
        onboarding_session = self._get_active_session(seller_user_id, session_id)
        payload = dict(onboarding_session.last_env_report or {})
        payload["compute_ready"] = detail or {}
        onboarding_session.last_env_report = payload
        onboarding_session.status = "compute_ready"
        onboarding_session.last_heartbeat_at = datetime.now(UTC)
        self.repository.save(onboarding_session)
        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=seller_user_id,
                actor_role="seller",
                event_type="seller_compute_ready_marked",
                target_type="seller_onboarding_session",
                target_id=str(onboarding_session.id),
                payload=detail or {},
            )
        return self._session_read(onboarding_session)

    def heartbeat(self, seller_user_id, session_id: str) -> SellerOnboardingSessionRead:
        onboarding_session = self._get_active_session(seller_user_id, session_id)
        onboarding_session.last_heartbeat_at = datetime.now(UTC)
        onboarding_session.expires_at = datetime.now(UTC) + timedelta(
            minutes=self.settings.seller_onboarding_session_ttl_minutes
        )
        self.repository.save(onboarding_session)
        return self._session_read(onboarding_session)

    def close(self, seller_user_id, session_id: str) -> SellerOnboardingSessionRead:
        onboarding_session = self._get_owned_session(seller_user_id, session_id)
        self._expire_if_needed(onboarding_session)
        if onboarding_session.status != "expired":
            onboarding_session.status = "closed"
            onboarding_session.last_heartbeat_at = datetime.now(UTC)
            self.repository.save(onboarding_session)
        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=seller_user_id,
                actor_role="seller",
                event_type="seller_onboarding_session_closed",
                target_type="seller_onboarding_session",
                target_id=str(onboarding_session.id),
                payload={"status": onboarding_session.status},
            )
        return self._session_read(onboarding_session)

    def claim_node(
        self,
        seller_user_id,
        node_ref: str,
        payload: SellerNodeClaimRequest,
    ) -> dict[str, Any]:
        onboarding_session = self._get_active_session(seller_user_id, payload.onboarding_session_id)
        requested_compute_node_id = onboarding_session.requested_compute_node_id or payload.compute_node_id
        requested_accelerator = payload.requested_accelerator or onboarding_session.requested_accelerator

        if (
            onboarding_session.requested_compute_node_id
            and requested_compute_node_id != onboarding_session.requested_compute_node_id
        ):
            raise ValueError("compute_node_id does not match the onboarding session.")
        if requested_accelerator != onboarding_session.requested_accelerator:
            raise ValueError("requested_accelerator does not match the onboarding session.")

        response = self.adapter_client.claim_node(
            {
                "node_ref": node_ref,
                "compute_node_id": requested_compute_node_id,
                "seller_user_id": str(seller_user_id),
                "accelerator": requested_accelerator,
            }
        )
        onboarding_session.status = "claimed"
        onboarding_session.requested_compute_node_id = requested_compute_node_id
        onboarding_session.last_heartbeat_at = datetime.now(UTC)
        self.repository.save(onboarding_session)
        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=seller_user_id,
                actor_role="seller",
                event_type="seller_node_claimed",
                target_type="seller_node",
                target_id=node_ref,
                payload={
                    "onboarding_session_id": str(onboarding_session.id),
                    "compute_node_id": requested_compute_node_id,
                    "requested_accelerator": requested_accelerator,
                },
            )
        return response

    def _get_owned_session(self, seller_user_id, session_id: str):
        onboarding_session = self.repository.get_for_seller(session_id, seller_user_id)
        if onboarding_session is None:
            raise ValueError("Onboarding session not found.")
        return onboarding_session

    def _get_active_session(self, seller_user_id, session_id: str):
        onboarding_session = self._get_owned_session(seller_user_id, session_id)
        self._expire_if_needed(onboarding_session)
        if onboarding_session.status not in ACTIVE_ONBOARDING_STATUSES:
            raise ValueError("Onboarding session is not active.")
        return onboarding_session

    def _expire_if_needed(self, onboarding_session) -> None:
        if onboarding_session.status in TERMINAL_ONBOARDING_STATUSES:
            return
        if onboarding_session.expires_at <= datetime.now(UTC):
            onboarding_session.status = "expired"
            onboarding_session.last_heartbeat_at = datetime.now(UTC)
            self.repository.save(onboarding_session)

    def _build_policy(self) -> SellerBuildPolicyRead:
        return SellerBuildPolicyRead(
            allowed_runtime_base_image=self.settings.managed_runtime_base_image,
            runtime_contract_version=self.settings.managed_runtime_contract_version,
            shell_agent_path=self.settings.managed_runtime_shell_agent_path,
            allowed_registry_host=self.settings.seller_allowed_registry_host,
            allowed_registry_namespace=self.settings.seller_allowed_registry_namespace,
            compute_substrate=self.settings.seller_compute_substrate,
            compute_host_type=self.settings.seller_compute_host_type,
            compute_network_mode=self.settings.seller_compute_network_mode,
            compute_runtime=self.settings.seller_compute_runtime,
            dockerfile_rules=[
                f"Dockerfile must use `FROM {self.settings.managed_runtime_base_image}`.",
                "All seller runtime images must be built in the Ubuntu compute environment, not in Windows Docker Desktop.",
                "Runtime contract labels and shell agent path must remain intact.",
                "Custom runtime changes are allowed only on top of the managed base image.",
                "GPU, CPU, and memory intent may be adjusted, but the final image must still pass platform validation.",
            ],
            allowed_resource_fields=["gpu_enabled", "gpu_count", "cpu_limit", "memory_limit_mb"],
            gpu_support_required=True,
        )

    def _build_codex_config_toml(self) -> str:
        provider_name = self.settings.seller_codex_model_provider
        lines = [
            f'model_provider = "{provider_name}"',
            f'model = "{self.settings.seller_codex_model}"',
            f'review_model = "{self.settings.seller_codex_review_model}"',
            f'model_reasoning_effort = "{self.settings.seller_codex_model_reasoning_effort}"',
            f"disable_response_storage = {self._toml_bool(self.settings.seller_codex_disable_response_storage)}",
            f'network_access = "{self.settings.seller_codex_network_access}"',
            "windows_wsl_setup_acknowledged = "
            f"{self._toml_bool(self.settings.seller_codex_windows_wsl_setup_acknowledged)}",
            f"model_context_window = {self.settings.seller_codex_model_context_window}",
            "model_auto_compact_token_limit = "
            f"{self.settings.seller_codex_model_auto_compact_token_limit}",
            "",
            f"[model_providers.{provider_name}]",
            f'name = "{provider_name}"',
            f'base_url = "{self.settings.seller_codex_base_url}"',
            f'wire_api = "{self.settings.seller_codex_wire_api}"',
            f"requires_openai_auth = {self._toml_bool(self.settings.seller_codex_requires_openai_auth)}",
        ]
        return "\n".join(lines) + "\n"

    def _build_windows_host_bootstrap(self) -> SellerWindowsHostBootstrapRead:
        return SellerWindowsHostBootstrapRead(
            workspace_root=r"D:\AI\Pivot_Client\seller_client",
            codex_mcp_server_name=self.settings.seller_codex_mcp_server_name,
            start_command=r"powershell -ExecutionPolicy Bypass -File bootstrap\windows\start_seller_console.ps1",
            seller_console_url="http://127.0.0.1:8901/",
        )

    def _build_ubuntu_bootstrap(
        self,
        join_material: dict[str, Any],
        *,
        requested_accelerator: str,
    ) -> SellerUbuntuBootstrapRead:
        required_packages = [
            item.strip() for item in self.settings.seller_compute_required_packages_csv.split(",") if item.strip()
        ]
        allowed_ips = [
            item.strip() for item in self.settings.seller_compute_wireguard_allowed_ips_csv.split(",") if item.strip()
        ]
        compute_peer = SellerWireGuardComputePeerRead(
            interface_name=self.settings.seller_compute_wireguard_interface_name,
            client_ip=self.settings.seller_compute_wireguard_client_ip,
            server_public_key=self.settings.seller_compute_wireguard_server_public_key,
            endpoint=self.settings.seller_compute_wireguard_endpoint,
            allowed_ips=allowed_ips,
            persistent_keepalive=self.settings.seller_compute_wireguard_persistent_keepalive,
        )
        swarm_join = SellerSwarmJoinBootstrapRead(
            join_token=join_material["join_token"],
            manager_addr=join_material["manager_addr"],
            manager_port=join_material["manager_port"],
            advertise_addr=self.settings.seller_compute_swarm_advertise_addr,
            data_path_addr=self.settings.seller_compute_swarm_data_path_addr,
            swarm_join_command=(
                f"docker swarm join --advertise-addr {self.settings.seller_compute_swarm_advertise_addr} "
                f"--data-path-addr {self.settings.seller_compute_swarm_data_path_addr} "
                f"--token {join_material['join_token']} {join_material['manager_addr']}:{join_material['manager_port']}"
            ),
        )
        verify_commands = [
            "python3 --version",
            "python3 -m venv /tmp/pivot-standard-venv && test -d /tmp/pivot-standard-venv",
            "wg --version",
            "docker --version",
            "docker info --format '{{json .Swarm}}'",
            f"timeout 10 bash -lc 'cat < /dev/null > /dev/tcp/{join_material['manager_addr']}/{join_material['manager_port']}'",
        ]
        if requested_accelerator == "gpu":
            verify_commands.append("nvidia-smi -L")
        standard_image = SellerSwarmStandardImageBootstrapRead(
            image_ref=self.settings.seller_swarm_standard_image_ref,
            description=self.settings.seller_swarm_standard_image_description,
            pull_command=f"docker pull {self.settings.seller_swarm_standard_image_ref}",
            verify_commands=verify_commands,
        )
        bash_script = f"""#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y {' '.join(required_packages)}
sudo mkdir -p {self.settings.seller_compute_ubuntu_runtime_root} {self.settings.seller_compute_ubuntu_workspace_root} {self.settings.seller_compute_ubuntu_logs_root}
echo "write WireGuard config to /etc/wireguard/{compute_peer.interface_name}.conf"
echo "{swarm_join.swarm_join_command}"
"""
        powershell_script = (
            f"wsl -d {self.settings.seller_compute_ubuntu_distribution_name} -- "
            f"bash -lc '{bash_script.strip()}'"
        )
        return SellerUbuntuBootstrapRead(
            distribution_name=self.settings.seller_compute_ubuntu_distribution_name,
            required_packages=required_packages,
            docker_engine_install_mode=self.settings.seller_compute_docker_engine_install_mode,
            workspace_root=self.settings.seller_compute_ubuntu_workspace_root,
            runtime_root=self.settings.seller_compute_ubuntu_runtime_root,
            logs_root=self.settings.seller_compute_ubuntu_logs_root,
            wireguard_compute_peer=compute_peer,
            swarm_join=swarm_join,
            seller_swarm_standard_image=standard_image,
            expected_node_addr=self.settings.seller_compute_swarm_advertise_addr,
            bootstrap_script_bash=bash_script,
            bootstrap_script_powershell=powershell_script,
        )

    def _resolve_codex_api_key(self) -> str | None:
        if self.settings.seller_codex_openai_api_key:
            return self.settings.seller_codex_openai_api_key
        if os.getenv("OPENAI_API_KEY"):
            return os.getenv("OPENAI_API_KEY")

        auth_path = Path.home() / ".codex" / "auth.json"
        if auth_path.exists():
            try:
                payload = json.loads(auth_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
            return payload.get("OPENAI_API_KEY")
        return None

    def _session_read(self, onboarding_session) -> SellerOnboardingSessionRead:
        env_payload = onboarding_session.last_env_report or {}
        return SellerOnboardingSessionRead(
            session_id=str(onboarding_session.id),
            status=onboarding_session.status,
            requested_accelerator=onboarding_session.requested_accelerator,
            requested_compute_node_id=onboarding_session.requested_compute_node_id,
            expires_at=onboarding_session.expires_at,
            last_heartbeat_at=onboarding_session.last_heartbeat_at,
            last_env_report=env_payload,
            last_windows_host_report=env_payload.get("windows_host"),
            last_ubuntu_compute_report=env_payload.get("ubuntu_compute"),
            compute_ready=onboarding_session.status in {"compute_ready", "claimed"},
            policy=self._build_policy(),
        )

    @staticmethod
    def _toml_bool(value: bool) -> str:
        return "true" if value else "false"
