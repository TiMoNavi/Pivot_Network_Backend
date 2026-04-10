from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend_app.db.base import Base
from backend_app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SellerOnboardingSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "seller_onboarding_sessions"

    seller_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active", index=True)
    requested_accelerator: Mapped[str] = mapped_column(String(64), nullable=False, server_default="gpu")
    requested_compute_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_env_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
