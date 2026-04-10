from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.db.models.audit import OperationLog
from backend_app.db.models.trade import AccessCode, BuyerOrder
from backend_app.repositories.buyer_repository import BuyerRepository
from backend_app.repositories.runtime_session_repository import RuntimeSessionRepository
from backend_app.schemas.platform import OperationLogRead, PlatformOrderRead, PlatformRuntimeSessionRead
from backend_app.services.audit_service import AuditService

ACTIVE_RUNTIME_SESSION_STATUSES = {"created", "provisioning", "running", "stopping"}
TERMINAL_RUNTIME_SESSION_STATUSES = {"removed", "stopped", "expired", "failed"}


class PlatformAdminService:
    def __init__(
        self,
        runtime_repository: RuntimeSessionRepository,
        buyer_repository: BuyerRepository,
        adapter_client: AdapterClient,
        audit_service: AuditService | None = None,
    ) -> None:
        self.runtime_repository = runtime_repository
        self.buyer_repository = buyer_repository
        self.adapter_client = adapter_client
        self.audit = audit_service

    def list_runtime_sessions(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
    ) -> list[PlatformRuntimeSessionRead]:
        rows = self.runtime_repository.list_sessions(limit=limit, status=status)
        return [self._platform_runtime_session_read(row) for row in rows]

    def get_runtime_session(self, session_id: str) -> PlatformRuntimeSessionRead:
        runtime_session = self.runtime_repository.get_session(session_id)
        if runtime_session is None:
            raise ValueError("Runtime session not found.")
        return self._platform_runtime_session_read(runtime_session)

    def refresh_runtime_session(self, session_id: str, *, reason: str = "manual") -> PlatformRuntimeSessionRead:
        runtime_session = self.runtime_repository.get_session(session_id)
        if runtime_session is None:
            raise ValueError("Runtime session not found.")

        request_payload = {"session_id": str(runtime_session.id)}
        try:
            bundle = self.adapter_client.inspect_runtime_bundle(request_payload)
        except AdapterClientError as exc:
            self._log_operation(
                operation_type="runtime_session_refresh",
                target_key=str(runtime_session.id),
                request_payload=request_payload,
                response_payload=exc.payload,
                status="failed",
                error_message=exc.detail,
            )
            self.buyer_repository.session.commit()
            raise

        self._log_operation(
            operation_type="runtime_session_refresh",
            target_key=str(runtime_session.id),
            request_payload=request_payload,
            response_payload=bundle,
            status="success",
        )
        self._apply_bundle_snapshot(runtime_session, bundle, event_type=f"runtime_session_refreshed:{reason}")
        return self._platform_runtime_session_read(runtime_session)

    def expire_runtime_session(
        self,
        session_id: str,
        *,
        force: bool = False,
        reason: str = "expired_reaper",
    ) -> PlatformRuntimeSessionRead:
        runtime_session = self.runtime_repository.get_session(session_id)
        if runtime_session is None:
            raise ValueError("Runtime session not found.")

        request_payload = {"session_id": str(runtime_session.id), "force": force}
        try:
            bundle = self.adapter_client.remove_runtime_bundle(request_payload)
        except AdapterClientError as exc:
            self._log_operation(
                operation_type="runtime_session_reap",
                target_key=str(runtime_session.id),
                request_payload=request_payload,
                response_payload=exc.payload,
                status="failed",
                error_message=exc.detail,
            )
            self.buyer_repository.session.commit()
            raise

        self._log_operation(
            operation_type="runtime_session_reap",
            target_key=str(runtime_session.id),
            request_payload=request_payload,
            response_payload=bundle,
            status="success",
        )
        self._apply_bundle_snapshot(
            runtime_session,
            bundle,
            event_type=f"runtime_session_removed:{reason}",
            terminal_order_status="expired",
        )
        if runtime_session.status not in TERMINAL_RUNTIME_SESSION_STATUSES:
            runtime_session.status = "expired"
        if runtime_session.ended_at is None:
            runtime_session.ended_at = datetime.now(UTC)
        return self._platform_runtime_session_read(runtime_session)

    def expire_access_code(self, access_code_id: str) -> AccessCode:
        access_code = self.buyer_repository.get_access_code_by_id(access_code_id)
        if access_code is None:
            raise ValueError("Access code not found.")
        if access_code.status != "issued":
            return access_code

        access_code.status = "expired"
        self.buyer_repository.session.add(access_code)
        order = self.buyer_repository.get_order(access_code.order_id, access_code.buyer_user_id)
        if order is not None and order.order_status == "access_code_issued":
            order.order_status = "access_code_expired"
            self.buyer_repository.session.add(order)
        if self.audit is not None:
            self.audit.log_operation(
                operation_type="access_code_reap",
                target_type="access_code",
                target_key=str(access_code.id),
                request_payload={"reason": "expired_reaper"},
                response_payload={"status": access_code.status},
                status="success",
            )
        return access_code

    def list_orders(self, *, limit: int = 100, status: str | None = None) -> list[PlatformOrderRead]:
        rows = self.buyer_repository.list_orders(limit=limit, status=status)
        return [self._order_read(row) for row in rows]

    def list_operation_logs(self, *, limit: int = 100, status: str | None = None) -> list[OperationLogRead]:
        statement = select(OperationLog)
        if status:
            statement = statement.where(OperationLog.status == status)
        statement = statement.order_by(OperationLog.created_at.desc()).limit(limit)
        rows = self.buyer_repository.session.scalars(statement)
        return [
            OperationLogRead(
                id=str(row.id),
                operation_type=row.operation_type,
                target_type=row.target_type,
                target_key=row.target_key,
                request_payload=row.request_payload,
                response_payload=row.response_payload,
                status=row.status,
                error_message=row.error_message,
                created_at=row.created_at,
            )
            for row in rows
        ]

    @staticmethod
    def is_runtime_session_active(status: str | None) -> bool:
        return (status or "") in ACTIVE_RUNTIME_SESSION_STATUSES

    def _apply_bundle_snapshot(
        self,
        runtime_session,
        bundle: dict[str, Any],
        *,
        event_type: str,
        terminal_order_status: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        connect_metadata = bundle.get("connect_metadata") or {}
        lease_metadata = bundle.get("wireguard_lease_metadata") or {}
        bundle_status = bundle.get("status") or runtime_session.status

        runtime_session.runtime_service_name = bundle.get("runtime_service_name") or runtime_session.runtime_service_name
        runtime_session.gateway_service_name = bundle.get("gateway_service_name") or runtime_session.gateway_service_name
        runtime_session.status = bundle_status
        runtime_session.last_synced_at = now

        if connect_metadata:
            runtime_session.gateway_host = connect_metadata.get("gateway_host") or runtime_session.gateway_host
            runtime_session.gateway_port = connect_metadata.get("gateway_port") or runtime_session.gateway_port
            runtime_session.connect_material_payload = connect_metadata
            runtime_session.connect_material_updated_at = now
        elif bundle_status in TERMINAL_RUNTIME_SESSION_STATUSES:
            runtime_session.connect_material_payload = {}
            runtime_session.connect_material_updated_at = now

        if bundle_status in TERMINAL_RUNTIME_SESSION_STATUSES and runtime_session.ended_at is None:
            runtime_session.ended_at = now
        if bundle_status in ACTIVE_RUNTIME_SESSION_STATUSES and runtime_session.started_at is None:
            runtime_session.started_at = now

        self.buyer_repository.session.add(runtime_session)

        if connect_metadata:
            self.runtime_repository.upsert_gateway_endpoint(
                runtime_session.id,
                protocol=connect_metadata.get("protocol") or "http",
                host=connect_metadata.get("gateway_host") or runtime_session.gateway_host or "",
                port=int(connect_metadata.get("gateway_port") or runtime_session.gateway_port or 0),
                access_url=connect_metadata.get("gateway_access_url") or "",
                path_prefix=connect_metadata.get("path_prefix"),
                access_mode=connect_metadata.get("access_mode") or "web_terminal",
                status=bundle_status,
                connect_metadata=connect_metadata,
                last_checked_at=now,
            )

        if lease_metadata:
            self.runtime_repository.upsert_wireguard_lease(
                runtime_session.id,
                lease_metadata.get("lease_type") or "buyer",
                public_key=lease_metadata.get("public_key"),
                server_public_key=lease_metadata.get("server_public_key"),
                client_address=lease_metadata.get("client_address"),
                endpoint_host=lease_metadata.get("endpoint_host"),
                endpoint_port=lease_metadata.get("endpoint_port"),
                allowed_ips=lease_metadata.get("allowed_ips"),
                persistent_keepalive=lease_metadata.get("persistent_keepalive"),
                server_interface=lease_metadata.get("server_interface"),
                status=lease_metadata.get("status") or ("removed" if bundle_status in TERMINAL_RUNTIME_SESSION_STATUSES else "applied"),
                lease_payload=lease_metadata,
                applied_at=now,
                removed_at=now if bundle_status in TERMINAL_RUNTIME_SESSION_STATUSES else None,
            )

        if terminal_order_status:
            order = self.buyer_repository.get_order(runtime_session.order_id, runtime_session.buyer_user_id)
            if order is not None:
                order.order_status = terminal_order_status
                self.buyer_repository.session.add(order)

        self.runtime_repository.add_event(runtime_session.id, event_type, bundle)

    def _platform_runtime_session_read(self, runtime_session) -> PlatformRuntimeSessionRead:
        gateway = self.runtime_repository.get_gateway_endpoint(runtime_session.id)
        lease = self.runtime_repository.get_wireguard_lease(runtime_session.id, "buyer")
        return PlatformRuntimeSessionRead(
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
            connect_material_updated_at=runtime_session.connect_material_updated_at,
            started_at=runtime_session.started_at,
            expires_at=runtime_session.expires_at,
            ended_at=runtime_session.ended_at,
            last_synced_at=runtime_session.last_synced_at,
            gateway_endpoint={
                "protocol": gateway.protocol,
                "host": gateway.host,
                "port": gateway.port,
                "access_url": gateway.access_url,
                "path_prefix": gateway.path_prefix,
                "access_mode": gateway.access_mode,
                "status": gateway.status,
                "connect_metadata": gateway.connect_metadata,
                "last_checked_at": gateway.last_checked_at,
            }
            if gateway is not None
            else None,
            wireguard_lease={
                "lease_type": lease.lease_type,
                "public_key": lease.public_key,
                "server_public_key": lease.server_public_key,
                "client_address": lease.client_address,
                "endpoint_host": lease.endpoint_host,
                "endpoint_port": lease.endpoint_port,
                "allowed_ips": lease.allowed_ips,
                "persistent_keepalive": lease.persistent_keepalive,
                "server_interface": lease.server_interface,
                "status": lease.status,
                "lease_payload": lease.lease_payload,
                "applied_at": lease.applied_at,
                "removed_at": lease.removed_at,
            }
            if lease is not None
            else None,
        )

    @staticmethod
    def _order_read(order: BuyerOrder) -> PlatformOrderRead:
        return PlatformOrderRead(
            id=str(order.id),
            buyer_user_id=str(order.buyer_user_id),
            offer_id=str(order.offer_id),
            order_no=order.order_no,
            order_status=order.order_status,
            issued_hourly_price=float(order.issued_hourly_price) if order.issued_hourly_price is not None else None,
            requested_duration_minutes=order.requested_duration_minutes,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    def _log_operation(
        self,
        *,
        operation_type: str,
        target_key: str,
        request_payload: dict[str, Any] | None,
        response_payload: dict[str, Any] | None,
        status: str,
        error_message: str | None = None,
    ) -> None:
        if self.audit is None:
            return
        self.audit.log_operation(
            operation_type=operation_type,
            target_type="runtime_session",
            target_key=target_key,
            request_payload=request_payload,
            response_payload=response_payload,
            status=status,
            error_message=error_message,
        )
