from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend_app.db.base import Base
from backend_app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SwarmCluster(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "swarm_clusters"

    cluster_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    adapter_base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    manager_host: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="unknown")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class SwarmNode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "swarm_nodes"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_clusters.id", ondelete="CASCADE"),
        nullable=False,
    )
    swarm_node_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    availability: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    compute_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    compute_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    seller_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    accelerator: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SwarmNodeLabel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "swarm_node_labels"
    __table_args__ = (UniqueConstraint("node_id", "label_key", name="uq_swarm_node_labels_node_key"),)

    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label_key: Mapped[str] = mapped_column(String(255), nullable=False)
    label_value: Mapped[str] = mapped_column(String(1024), nullable=False)


class SwarmService(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "swarm_services"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_clusters.id", ondelete="CASCADE"),
        nullable=False,
    )
    swarm_service_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    service_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="other")
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    image: Mapped[str] = mapped_column(String(512), nullable=False)
    desired_replicas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    running_replicas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    seller_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    runtime_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SwarmTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "swarm_tasks"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    swarm_task_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    desired_state: Mapped[str] = mapped_column(String(64), nullable=False)
    current_state: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SwarmSyncRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "swarm_sync_runs"

    sync_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    nodes_changed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    services_changed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tasks_changed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class SwarmSyncEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "swarm_sync_events"

    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    before_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
