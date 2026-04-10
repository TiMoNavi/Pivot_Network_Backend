from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend_app.db.base import Base
from backend_app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BuyerRuntimeClientSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "buyer_runtime_client_sessions"
    __table_args__ = (
        UniqueConstraint("runtime_session_id", name="uq_buyer_runtime_client_sessions_runtime_session_id"),
    )

    runtime_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runtime_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_env_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
