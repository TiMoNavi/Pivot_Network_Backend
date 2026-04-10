from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.repositories.buyer_repository import BuyerRepository
from backend_app.repositories.runtime_session_repository import RuntimeSessionRepository
from backend_app.schemas.platform import MaintenanceRunResponse
from backend_app.services.audit_service import AuditService
from backend_app.services.platform_admin_service import PlatformAdminService


@dataclass
class RuntimeRefreshWorker:
    session_factory: sessionmaker[Session]
    adapter_factory: Callable[[], AdapterClient]
    stale_after_minutes: int = 2

    def run_once(self, *, limit: int = 25) -> MaintenanceRunResponse:
        with self.session_factory() as discovery_session:
            repository = RuntimeSessionRepository(discovery_session)
            stale_before = datetime.now(UTC) - timedelta(minutes=self.stale_after_minutes)
            session_ids = [str(row.id) for row in repository.list_refresh_candidates(stale_before=stale_before, limit=limit)]

        details: list[dict[str, str]] = []
        success_count = 0
        failed_count = 0
        for session_id in session_ids:
            with self.session_factory() as session:
                service = PlatformAdminService(
                    RuntimeSessionRepository(session),
                    BuyerRepository(session),
                    self.adapter_factory(),
                    audit_service=AuditService(session),
                )
                try:
                    refreshed = service.refresh_runtime_session(session_id, reason="worker")
                    session.commit()
                    success_count += 1
                    details.append(
                        {
                            "session_id": session_id,
                            "status": refreshed.status,
                            "result": "refreshed",
                        }
                    )
                except (AdapterClientError, ValueError) as exc:
                    session.rollback()
                    failed_count += 1
                    details.append(
                        {
                            "session_id": session_id,
                            "status": "failed",
                            "detail": str(exc),
                        }
                    )

        return MaintenanceRunResponse(
            job_name="runtime_refresh",
            status="success" if failed_count == 0 else "partial_failure",
            processed_count=len(session_ids),
            success_count=success_count,
            failed_count=failed_count,
            details=details,
        )
