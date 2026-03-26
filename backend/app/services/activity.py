from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.activity import ActivityEvent


def log_activity(
    db: Session,
    *,
    seller_user_id: int | None,
    event_type: str,
    summary: str,
    detail: str | None = None,
    node_id: int | None = None,
    image_id: int | None = None,
    metadata: dict | None = None,
) -> ActivityEvent:
    event = ActivityEvent(
        seller_user_id=seller_user_id,
        node_id=node_id,
        image_id=image_id,
        event_type=event_type,
        summary=summary,
        detail=detail,
        event_metadata=metadata or {},
    )
    db.add(event)
    db.flush()
    return event
