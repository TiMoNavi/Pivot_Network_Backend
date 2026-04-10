from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.db.models.swarm import SwarmNode
from backend_app.repositories.buyer_repository import BuyerRepository
from backend_app.repositories.runtime_session_repository import RuntimeSessionRepository
from backend_app.schemas.runtime_session import (
    BuyerRuntimeClientBootstrapConfigRead,
    BuyerConnectMaterialResponse,
    BuyerRuntimeSessionCreateRequest,
    BuyerRuntimeSessionRead,
)
from backend_app.services.audit_service import AuditService


class RuntimeSessionService:
    def __init__(
        self,
        buyer_repository: BuyerRepository,
        runtime_repository: RuntimeSessionRepository,
        adapter_client: AdapterClient,
        audit_service: AuditService | None = None,
    ) -> None:
        self.buyer_repository = buyer_repository
        self.runtime_repository = runtime_repository
        self.adapter_client = adapter_client
        self.audit = audit_service

    def create_session(self, buyer_user_id: str, payload: BuyerRuntimeSessionCreateRequest) -> BuyerRuntimeSessionRead:
        access_code = self.buyer_repository.get_access_code(payload.access_code, buyer_user_id)
        if access_code is None:
            raise ValueError("Access code not found.")
        if access_code.status != "redeemed":
            raise ValueError("Access code must be redeemed before session creation.")
        active = self.runtime_repository.get_active_for_access_code(access_code.id)
        if active is not None:
            raise ValueError("An active runtime session already exists for this access code.")

        order = self.buyer_repository.get_order(access_code.order_id, buyer_user_id)
        if order is None:
            raise ValueError("Order not found.")
        offer = self.buyer_repository.get_offer(order.offer_id)
        if offer is None:
            raise ValueError("Offer not found.")
        seller_node = self.buyer_repository.session.scalar(
            select(SwarmNode).where(SwarmNode.swarm_node_id == offer.swarm_node_id)
        )

        runtime_session = self.runtime_repository.create_session(
            buyer_user_id=order.buyer_user_id,
            seller_node_id=seller_node.id if seller_node is not None else None,
            offer_id=order.offer_id,
            order_id=order.id,
            access_code_id=access_code.id,
            runtime_image_ref=offer.runtime_image_ref,
            status="created",
            network_mode=payload.network_mode,
            expires_at=datetime.now(UTC) + timedelta(minutes=order.requested_duration_minutes),
        )

        bundle_payload = {
            "session_id": str(runtime_session.id),
            "offer_id": str(offer.id),
            "node_ref": offer.swarm_node_id,
            "runtime_image_ref": offer.runtime_image_ref,
            "requested_duration_minutes": order.requested_duration_minutes,
            "buyer_user_id": str(order.buyer_user_id),
            "network_mode": payload.network_mode,
            "buyer_network": {
                "public_key": payload.wireguard_public_key,
            },
        }
        bundle = self.adapter_client.create_runtime_bundle(bundle_payload)

        runtime_session.runtime_service_name = bundle.get("runtime_service_name")
        runtime_session.gateway_service_name = bundle.get("gateway_service_name")
        runtime_session.status = bundle.get("status") or "provisioning"
        runtime_session.runtime_image_ref = offer.runtime_image_ref
        runtime_session.gateway_host = (bundle.get("connect_metadata") or {}).get("gateway_host")
        runtime_session.gateway_port = (bundle.get("connect_metadata") or {}).get("gateway_port")
        runtime_session.connect_material_payload = bundle.get("connect_metadata") or {}
        runtime_session.connect_material_updated_at = datetime.now(UTC)
        runtime_session.started_at = datetime.now(UTC)
        runtime_session.last_synced_at = datetime.now(UTC)

        gateway_metadata = bundle.get("connect_metadata") or {}
        self.runtime_repository.upsert_gateway_endpoint(
            runtime_session.id,
            protocol="http",
            host=gateway_metadata.get("gateway_host") or "",
            port=int(gateway_metadata.get("gateway_port") or 0),
            access_url=gateway_metadata.get("gateway_access_url") or "",
            path_prefix=None,
            access_mode=gateway_metadata.get("access_mode") or "web_terminal",
            status=runtime_session.status,
            connect_metadata=gateway_metadata,
            last_checked_at=datetime.now(UTC),
        )

        lease_metadata = bundle.get("wireguard_lease_metadata") or {}
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

        order.order_status = "session_started"
        self.buyer_repository.session.add(order)
        self.buyer_repository.session.add(runtime_session)
        self.runtime_repository.add_event(runtime_session.id, "session_created", bundle)

        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=buyer_user_id,
                actor_role="buyer",
                event_type="runtime_session_created",
                target_type="runtime_session",
                target_id=str(runtime_session.id),
                payload={"bundle_status": bundle.get("status")},
            )

        return self._session_read(runtime_session)

    def get_buyer_session(self, buyer_user_id: str, session_id: str) -> BuyerRuntimeSessionRead:
        runtime_session = self.runtime_repository.get_buyer_session(buyer_user_id, session_id)
        if runtime_session is None:
            raise ValueError("Runtime session not found.")
        return self._session_read(runtime_session)

    def get_connect_material(self, buyer_user_id: str, session_id: str) -> BuyerConnectMaterialResponse:
        runtime_session = self.runtime_repository.get_buyer_session(buyer_user_id, session_id)
        if runtime_session is None:
            raise ValueError("Runtime session not found.")

        bundle = self.adapter_client.inspect_runtime_bundle({"session_id": session_id})
        runtime_session.status = bundle.get("status") or runtime_session.status
        runtime_session.connect_material_payload = bundle.get("connect_metadata") or runtime_session.connect_material_payload
        runtime_session.connect_material_updated_at = datetime.now(UTC)
        runtime_session.last_synced_at = datetime.now(UTC)
        self.buyer_repository.session.add(runtime_session)

        gateway_metadata = bundle.get("connect_metadata") or {}
        if gateway_metadata:
            self.runtime_repository.upsert_gateway_endpoint(
                runtime_session.id,
                protocol="http",
                host=gateway_metadata.get("gateway_host") or "",
                port=int(gateway_metadata.get("gateway_port") or 0),
                access_url=gateway_metadata.get("gateway_access_url") or "",
                path_prefix=None,
                access_mode=gateway_metadata.get("access_mode") or "web_terminal",
                status=runtime_session.status,
                connect_metadata=gateway_metadata,
                last_checked_at=datetime.now(UTC),
            )

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

        self.runtime_repository.add_event(runtime_session.id, "connect_material_refreshed", bundle)

        return BuyerConnectMaterialResponse(
            session_id=str(runtime_session.id),
            status=runtime_session.status,
            connect_material=runtime_session.connect_material_payload or {},
            public_gateway_access_url=(runtime_session.connect_material_payload or {}).get("public_gateway_access_url"),
            wireguard_gateway_access_url=(runtime_session.connect_material_payload or {}).get("wireguard_gateway_access_url"),
            shell_embed_url=(runtime_session.connect_material_payload or {}).get("shell_embed_url"),
            workspace_sync_url=(runtime_session.connect_material_payload or {}).get("workspace_sync_url"),
            workspace_root=(runtime_session.connect_material_payload or {}).get("workspace_root"),
            wireguard_profile_fields={
                "server_public_key": lease_metadata.get("server_public_key"),
                "client_address": lease_metadata.get("client_address"),
                "endpoint_host": lease_metadata.get("endpoint_host"),
                "endpoint_port": lease_metadata.get("endpoint_port"),
                "allowed_ips": (runtime_session.connect_material_payload or {}).get("client_allowed_ips")
                or lease_metadata.get("client_allowed_ips")
                or lease_metadata.get("allowed_ips"),
                "persistent_keepalive": lease_metadata.get("persistent_keepalive"),
            }
            if lease_metadata
            else None,
            wireguard_lease=lease_metadata or None,
        )

    def stop_session(self, buyer_user_id: str, session_id: str) -> BuyerRuntimeSessionRead:
        runtime_session = self.runtime_repository.get_buyer_session(buyer_user_id, session_id)
        if runtime_session is None:
            raise ValueError("Runtime session not found.")

        bundle = self.adapter_client.remove_runtime_bundle({"session_id": session_id, "force": False})
        runtime_session.status = bundle.get("status") or "stopped"
        runtime_session.ended_at = datetime.now(UTC)
        runtime_session.last_synced_at = datetime.now(UTC)
        runtime_session.connect_material_payload = {}
        self.buyer_repository.session.add(runtime_session)
        order = self.buyer_repository.get_order(runtime_session.order_id, buyer_user_id)
        if order is not None:
            order.order_status = "completed"
            self.buyer_repository.session.add(order)

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
                status=lease_metadata.get("status") or "removed",
                lease_payload=lease_metadata,
                applied_at=datetime.now(UTC),
                removed_at=datetime.now(UTC),
            )

        self.runtime_repository.add_event(runtime_session.id, "session_stopped", bundle)
        return self._session_read(runtime_session)

    @staticmethod
    def _session_read(runtime_session) -> BuyerRuntimeSessionRead:
        return BuyerRuntimeSessionRead(
            id=str(runtime_session.id),
            buyer_user_id=str(runtime_session.buyer_user_id),
            seller_node_id=str(runtime_session.seller_node_id) if runtime_session.seller_node_id else None,
            offer_id=str(runtime_session.offer_id),
            order_id=str(runtime_session.order_id),
            access_code_id=str(runtime_session.access_code_id),
            runtime_image_ref=runtime_session.runtime_image_ref,
            runtime_service_name=runtime_session.runtime_service_name,
            gateway_service_name=runtime_session.gateway_service_name,
            status=runtime_session.status,
            gateway_host=runtime_session.gateway_host,
            gateway_port=runtime_session.gateway_port,
            network_mode=runtime_session.network_mode,
            connect_material_payload=runtime_session.connect_material_payload,
            public_gateway_access_url=(runtime_session.connect_material_payload or {}).get("public_gateway_access_url"),
            wireguard_gateway_access_url=(runtime_session.connect_material_payload or {}).get("wireguard_gateway_access_url"),
            shell_embed_url=(runtime_session.connect_material_payload or {}).get("shell_embed_url"),
            workspace_sync_url=(runtime_session.connect_material_payload or {}).get("workspace_sync_url"),
            workspace_root=(runtime_session.connect_material_payload or {}).get("workspace_root"),
            connect_material_updated_at=runtime_session.connect_material_updated_at,
            started_at=runtime_session.started_at,
            expires_at=runtime_session.expires_at,
            ended_at=runtime_session.ended_at,
            last_synced_at=runtime_session.last_synced_at,
        )
