from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend_app.db.base import Base
from backend_app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ImageArtifact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "image_artifacts"

    seller_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    swarm_node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    repository: Mapped[str] = mapped_column(String(255), nullable=False)
    tag: Mapped[str] = mapped_column(String(128), nullable=False)
    digest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registry: Mapped[str] = mapped_column(String(255), nullable=False)
    base_image_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    runtime_contract_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="reported")


class ImageOffer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "image_offers"

    seller_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    swarm_node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    image_artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("image_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_image_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    offer_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="reported")
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    validation_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shell_agent_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    runtime_contract_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    probe_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    probe_measured_capabilities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    current_billable_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    pricing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_probed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OfferPriceSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "offer_price_snapshots"

    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("image_offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    billable_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_components: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NodeCapabilitySnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "node_capability_snapshots"

    swarm_node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cpu_logical: Mapped[int | None] = mapped_column(nullable=True)
    memory_total_mb: Mapped[int | None] = mapped_column(nullable=True)
    gpu_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    probe_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    probed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
