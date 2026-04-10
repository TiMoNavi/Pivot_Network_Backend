from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend_app.db.models.audit import ActivityEvent, OperationLog


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def log_activity(
        self,
        *,
        actor_user_id,
        actor_role: str,
        event_type: str,
        target_type: str,
        target_id: str,
        payload: dict,
    ) -> None:
        event = ActivityEvent(
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        self.session.add(event)
        self.session.flush()

    def log_operation(
        self,
        *,
        operation_type: str,
        target_type: str,
        target_key: str,
        request_payload: dict | None,
        response_payload: dict | None,
        status: str,
        error_message: str | None = None,
    ) -> None:
        log = OperationLog(
            operation_type=operation_type,
            target_type=target_type,
            target_key=target_key,
            request_payload=request_payload,
            response_payload=response_payload,
            status=status,
            error_message=error_message,
            created_at=datetime.now(UTC),
        )
        self.session.add(log)
        self.session.flush()
