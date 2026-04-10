from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend_app.db.base import Base
from backend_app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RuntimeSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "runtime_sessions"

    buyer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seller_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("image_offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("buyer_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_codes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_image_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    runtime_service_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gateway_service_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="created", index=True)
    gateway_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gateway_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    network_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    connect_material_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    connect_material_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class RuntimeSessionEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "runtime_session_events"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runtime_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GatewayEndpoint(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "gateway_endpoints"
    __table_args__ = (UniqueConstraint("runtime_session_id", name="uq_gateway_endpoints_runtime_session_id"),)

    runtime_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runtime_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol: Mapped[str] = mapped_column(String(32), nullable=False, server_default="http")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    access_url: Mapped[str] = mapped_column(String(512), nullable=False)
    path_prefix: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="web_terminal")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="provisioning")
    connect_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WireGuardLease(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "wireguard_leases"
    __table_args__ = (UniqueConstraint("runtime_session_id", "lease_type", name="uq_wireguard_leases_session_type"),)

    runtime_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runtime_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lease_type: Mapped[str] = mapped_column(String(32), nullable=False)
    public_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    server_public_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    endpoint_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endpoint_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_ips: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    persistent_keepalive: Mapped[int | None] = mapped_column(Integer, nullable=True)
    server_interface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="requested", index=True)
    lease_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
