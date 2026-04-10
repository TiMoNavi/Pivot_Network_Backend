from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.core.config import get_settings
from backend_app.repositories.buyer_runtime_client_repository import BuyerRuntimeClientRepository
from backend_app.repositories.runtime_session_repository import RuntimeSessionRepository
from backend_app.schemas.runtime_session import (
    BuyerRuntimeClientBootstrapConfigRead,
    BuyerRuntimeClientSessionRead,
    WireGuardProfileRead,
)
from backend_app.services.audit_service import AuditService

ACTIVE_CLIENT_SESSION_STATUSES = {"active"}
TERMINAL_CLIENT_SESSION_STATUSES = {"closed", "expired"}


class BuyerRuntimeClientService:
    def __init__(
        self,
        session: Session,
        runtime_repository: RuntimeSessionRepository,
        adapter_client: AdapterClient,
        audit_service: AuditService | None = None,
    ) -> None:
        self.session = session
        self.runtime_repository = runtime_repository
        self.adapter_client = adapter_client
        self.client_repository = BuyerRuntimeClientRepository(session)
        self.audit = audit_service
        self.settings = get_settings()

    def get_bootstrap_config(self, buyer_user_id, session_id: str) -> BuyerRuntimeClientBootstrapConfigRead:
        runtime_session = self._get_buyer_runtime_session(buyer_user_id, session_id)
        self._refresh_runtime_snapshot(runtime_session)
        client_session = self._upsert_client_session(runtime_session.id, buyer_user_id, status="active")
        connect_material = runtime_session.connect_material_payload or {}
        profile = self._wireguard_profile(connect_material)
        return BuyerRuntimeClientBootstrapConfigRead(
            runtime_session_id=str(runtime_session.id),
            client_session=self._client_session_read(client_session),
            codex_config_toml=self._build_codex_config_toml(),
            codex_auth_json=json.dumps(
                {
                    "auth_mode": "openai_api_key",
                    "OPENAI_API_KEY": self._resolve_codex_api_key(),
                },
                indent=2,
            ),
            shell_embed_url=connect_material.get("shell_embed_url"),
            public_gateway_access_url=connect_material.get("public_gateway_access_url"),
            wireguard_gateway_access_url=connect_material.get("wireguard_gateway_access_url"),
            workspace_sync_url=connect_material.get("workspace_sync_url"),
            workspace_root=connect_material.get("workspace_root"),
            wireguard_profile=self._wireguard_profile(connect_material),
            codex_mcp_launch={
                "name": self.settings.buyer_codex_mcp_server_name,
                "transport": "stdio",
                "command": ["python", "-m", "buyer_client_app.mcp_server"],
            },
        )

    def get_client_session(self, buyer_user_id, session_id: str) -> BuyerRuntimeClientSessionRead:
        runtime_session = self._get_buyer_runtime_session(buyer_user_id, session_id)
        client_session = self._get_active_or_existing_client_session(runtime_session.id, buyer_user_id)
        return self._client_session_read(client_session)

    def report_env(self, buyer_user_id, session_id: str, env_report: dict[str, Any]) -> BuyerRuntimeClientSessionRead:
        runtime_session = self._get_buyer_runtime_session(buyer_user_id, session_id)
        client_session = self._get_active_or_existing_client_session(runtime_session.id, buyer_user_id)
        self._expire_if_needed(client_session)
        if client_session.status not in ACTIVE_CLIENT_SESSION_STATUSES:
            raise ValueError("Buyer runtime client session is not active.")
        client_session = self.client_repository.upsert(
            runtime_session.id,
            buyer_user_id,
            status=client_session.status,
            expires_at=client_session.expires_at,
            last_heartbeat_at=datetime.now(UTC),
            last_env_report=env_report,
        )
        return self._client_session_read(client_session)

    def heartbeat(self, buyer_user_id, session_id: str) -> BuyerRuntimeClientSessionRead:
        runtime_session = self._get_buyer_runtime_session(buyer_user_id, session_id)
        client_session = self._get_active_or_existing_client_session(runtime_session.id, buyer_user_id)
        self._expire_if_needed(client_session)
        if client_session.status not in ACTIVE_CLIENT_SESSION_STATUSES:
            raise ValueError("Buyer runtime client session is not active.")
        new_expiry = min(
            runtime_session.expires_at,
            datetime.now(UTC) + timedelta(minutes=self.settings.buyer_runtime_client_session_ttl_minutes),
        )
        client_session = self.client_repository.upsert(
            runtime_session.id,
            buyer_user_id,
            status="active",
            expires_at=new_expiry,
            last_heartbeat_at=datetime.now(UTC),
            last_env_report=client_session.last_env_report,
        )
        return self._client_session_read(client_session)

    def close(self, buyer_user_id, session_id: str) -> BuyerRuntimeClientSessionRead:
        runtime_session = self._get_buyer_runtime_session(buyer_user_id, session_id)
        client_session = self._get_active_or_existing_client_session(runtime_session.id, buyer_user_id)
        self._expire_if_needed(client_session)
        if client_session.status != "expired":
            client_session = self.client_repository.upsert(
                runtime_session.id,
                buyer_user_id,
                status="closed",
                expires_at=client_session.expires_at,
                last_heartbeat_at=datetime.now(UTC),
                last_env_report=client_session.last_env_report,
            )
        return self._client_session_read(client_session)

    def _get_buyer_runtime_session(self, buyer_user_id, session_id: str):
        runtime_session = self.runtime_repository.get_buyer_session(buyer_user_id, session_id)
        if runtime_session is None:
            raise ValueError("Runtime session not found.")
        return runtime_session

    def _get_active_or_existing_client_session(self, runtime_session_id, buyer_user_id):
        client_session = self.client_repository.get_for_runtime_session(runtime_session_id, buyer_user_id)
        if client_session is None:
            raise ValueError("Buyer runtime client session not found.")
        return client_session

    def _upsert_client_session(self, runtime_session_id, buyer_user_id, *, status: str):
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.buyer_runtime_client_session_ttl_minutes)
        return self.client_repository.upsert(
            runtime_session_id,
            buyer_user_id,
            status=status,
            expires_at=expires_at,
            last_heartbeat_at=datetime.now(UTC),
            last_env_report=None,
        )

    def _refresh_runtime_snapshot(self, runtime_session) -> None:
        bundle = self.adapter_client.inspect_runtime_bundle({"session_id": str(runtime_session.id)})
        connect_material = bundle.get("connect_metadata") or {}
        runtime_session.status = bundle.get("status") or runtime_session.status
        runtime_session.connect_material_payload = connect_material
        runtime_session.connect_material_updated_at = datetime.now(UTC)
        runtime_session.gateway_host = (
            connect_material.get("gateway_host")
            or connect_material.get("wireguard_gateway_host")
            or runtime_session.gateway_host
        )
        runtime_session.gateway_port = (
            connect_material.get("gateway_port")
            or connect_material.get("wireguard_gateway_port")
            or runtime_session.gateway_port
        )
        runtime_session.last_synced_at = datetime.now(UTC)
        self.session.add(runtime_session)
        lease_metadata = bundle.get("wireguard_lease_metadata") or {}
        if lease_metadata:
            self.runtime_repository.upsert_wireguard_lease(
                runtime_session.id,
                "buyer",
                public_key=lease_metadata.get("public_key"),
                server_public_key=lease_metadata.get("server_public_key"),
                client_address=lease_metadata.get("client_address"),
                endpoint_host=lease_metadata.get("endpoint_host"),
                endpoint_port=lease_metadata.get("endpoint_port"),
                allowed_ips=lease_metadata.get("allowed_ips"),
                persistent_keepalive=lease_metadata.get("persistent_keepalive"),
                server_interface=lease_metadata.get("server_interface"),
                status=lease_metadata.get("status") or "applied",
                lease_payload=lease_metadata,
                applied_at=datetime.now(UTC),
                removed_at=None,
            )
        self.session.flush()

    def _wireguard_profile(self, connect_material: dict[str, Any]) -> WireGuardProfileRead:
        return WireGuardProfileRead(
            server_public_key=connect_material.get("server_public_key"),
            client_address=connect_material.get("client_address"),
            endpoint_host=connect_material.get("endpoint_host"),
            endpoint_port=connect_material.get("endpoint_port"),
            allowed_ips=connect_material.get("client_allowed_ips") or connect_material.get("allowed_ips") or [],
            persistent_keepalive=connect_material.get("persistent_keepalive"),
        )

    def _client_session_read(self, client_session) -> BuyerRuntimeClientSessionRead:
        return BuyerRuntimeClientSessionRead(
            status=client_session.status,
            expires_at=client_session.expires_at,
            last_heartbeat_at=client_session.last_heartbeat_at,
            last_env_report=client_session.last_env_report,
        )

    def _expire_if_needed(self, client_session) -> None:
        if client_session.status in TERMINAL_CLIENT_SESSION_STATUSES:
            return
        if client_session.expires_at <= datetime.now(UTC):
            client_session.status = "expired"
            client_session.last_heartbeat_at = datetime.now(UTC)
            self.session.add(client_session)
            self.session.flush()

    def _resolve_codex_api_key(self) -> str:
        if self.settings.buyer_codex_openai_api_key:
            return self.settings.buyer_codex_openai_api_key
        if os.getenv("OPENAI_API_KEY"):
            return os.getenv("OPENAI_API_KEY")
        auth_path = Path.home() / ".codex" / "auth.json"
        if auth_path.exists():
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
            api_key = payload.get("OPENAI_API_KEY")
            if api_key:
                return api_key
        raise RuntimeError("Buyer runtime Codex auth is not configured.")

    def _build_codex_config_toml(self) -> str:
        provider_name = self.settings.buyer_codex_model_provider
        lines = [
            f'model_provider = "{provider_name}"',
            f'model = "{self.settings.buyer_codex_model}"',
            f'review_model = "{self.settings.buyer_codex_review_model}"',
            f'model_reasoning_effort = "{self.settings.buyer_codex_model_reasoning_effort}"',
            f"disable_response_storage = {self._toml_bool(self.settings.buyer_codex_disable_response_storage)}",
            f'network_access = "{self.settings.buyer_codex_network_access}"',
            "windows_wsl_setup_acknowledged = "
            f"{self._toml_bool(self.settings.buyer_codex_windows_wsl_setup_acknowledged)}",
            f"model_context_window = {self.settings.buyer_codex_model_context_window}",
            "model_auto_compact_token_limit = "
            f"{self.settings.buyer_codex_model_auto_compact_token_limit}",
            "",
            f"[model_providers.{provider_name}]",
            f'name = "{provider_name}"',
            f'base_url = "{self.settings.buyer_codex_base_url}"',
            f'wire_api = "{self.settings.buyer_codex_wire_api}"',
            f"requires_openai_auth = {self._toml_bool(self.settings.buyer_codex_requires_openai_auth)}",
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _toml_bool(value: bool) -> str:
        return "true" if value else "false"
