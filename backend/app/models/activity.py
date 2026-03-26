from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, JSON, Column

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id = Column(Integer, primary_key=True)
    seller_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), index=True, nullable=True)
    image_id = Column(Integer, ForeignKey("image_artifacts.id"), index=True, nullable=True)
    event_type = Column(String(100), index=True, nullable=False)
    summary = Column(String(255), nullable=False)
    detail = Column(Text, nullable=True)
    event_metadata = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
