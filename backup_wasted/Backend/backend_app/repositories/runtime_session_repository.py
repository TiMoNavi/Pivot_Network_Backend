from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend_app.db.models.runtime_session import GatewayEndpoint, RuntimeSession, RuntimeSessionEvent, WireGuardLease


class RuntimeSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_session(self, **kwargs) -> RuntimeSession:
        runtime_session = RuntimeSession(**kwargs)
        self.session.add(runtime_session)
        self.session.flush()
        return runtime_session

    def get_buyer_session(self, buyer_user_id, session_id) -> RuntimeSession | None:
        statement = select(RuntimeSession).where(
            RuntimeSession.id == session_id,
            RuntimeSession.buyer_user_id == buyer_user_id,
        )
        return self.session.scalar(statement)

    def get_session(self, session_id) -> RuntimeSession | None:
        return self.session.scalar(select(RuntimeSession).where(RuntimeSession.id == session_id))

    def get_active_for_access_code(self, access_code_id) -> RuntimeSession | None:
        statement = select(RuntimeSession).where(
            RuntimeSession.access_code_id == access_code_id,
            RuntimeSession.status.in_(["created", "provisioning", "running", "stopping"]),
        )
        return self.session.scalar(statement)

    def list_sessions(self, *, limit: int = 100, status: str | None = None) -> list[RuntimeSession]:
        statement = select(RuntimeSession)
        if status:
            statement = statement.where(RuntimeSession.status == status)
        statement = statement.order_by(RuntimeSession.created_at.desc()).limit(limit)
        return list(self.session.scalars(statement))

    def list_refresh_candidates(
        self,
        *,
        stale_before: datetime,
        limit: int = 50,
        statuses: tuple[str, ...] = ("created", "provisioning", "running", "stopping"),
    ) -> list[RuntimeSession]:
        statement = (
            select(RuntimeSession)
            .where(
                RuntimeSession.status.in_(statuses),
                or_(
                    RuntimeSession.last_synced_at.is_(None),
                    RuntimeSession.last_synced_at <= stale_before,
                ),
            )
            .order_by(RuntimeSession.last_synced_at.asc().nullsfirst(), RuntimeSession.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_expired_active_sessions(
        self,
        *,
        now: datetime,
        limit: int = 50,
        statuses: tuple[str, ...] = ("created", "provisioning", "running", "stopping"),
    ) -> list[RuntimeSession]:
        statement = (
            select(RuntimeSession)
            .where(
                RuntimeSession.status.in_(statuses),
                RuntimeSession.expires_at <= now,
            )
            .order_by(RuntimeSession.expires_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def upsert_gateway_endpoint(self, runtime_session_id, **kwargs) -> GatewayEndpoint:
        endpoint = self.session.scalar(select(GatewayEndpoint).where(GatewayEndpoint.runtime_session_id == runtime_session_id))
        if endpoint is None:
            endpoint = GatewayEndpoint(runtime_session_id=runtime_session_id, **kwargs)
            self.session.add(endpoint)
            self.session.flush()
            return endpoint
        for key, value in kwargs.items():
            setattr(endpoint, key, value)
        self.session.add(endpoint)
        self.session.flush()
        return endpoint

    def upsert_wireguard_lease(self, runtime_session_id, lease_type: str, **kwargs) -> WireGuardLease:
        lease = self.session.scalar(
            select(WireGuardLease).where(
                WireGuardLease.runtime_session_id == runtime_session_id,
                WireGuardLease.lease_type == lease_type,
            )
        )
        if lease is None:
            lease = WireGuardLease(runtime_session_id=runtime_session_id, lease_type=lease_type, **kwargs)
            self.session.add(lease)
            self.session.flush()
            return lease
        for key, value in kwargs.items():
            setattr(lease, key, value)
        self.session.add(lease)
        self.session.flush()
        return lease

    def add_event(self, session_id, event_type: str, event_payload: dict | None) -> RuntimeSessionEvent:
        event = RuntimeSessionEvent(
            session_id=session_id,
            event_type=event_type,
            event_payload=event_payload,
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
        self.session.add(event)
        self.session.flush()
        return event

    def get_gateway_endpoint(self, runtime_session_id) -> GatewayEndpoint | None:
        return self.session.scalar(select(GatewayEndpoint).where(GatewayEndpoint.runtime_session_id == runtime_session_id))

    def get_wireguard_lease(self, runtime_session_id, lease_type: str = "buyer") -> WireGuardLease | None:
        return self.session.scalar(
            select(WireGuardLease).where(
                WireGuardLease.runtime_session_id == runtime_session_id,
                WireGuardLease.lease_type == lease_type,
            )
        )
