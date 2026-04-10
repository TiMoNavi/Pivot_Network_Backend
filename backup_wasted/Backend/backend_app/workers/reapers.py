from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.repositories.buyer_repository import BuyerRepository
from backend_app.repositories.runtime_session_repository import RuntimeSessionRepository
from backend_app.schemas.platform import MaintenanceRunResponse
from backend_app.services.audit_service import AuditService
from backend_app.services.platform_admin_service import PlatformAdminService


@dataclass
class AccessCodeReaper:
    session_factory: sessionmaker[Session]

    def run_once(self, *, limit: int = 100) -> MaintenanceRunResponse:
        with self.session_factory() as discovery_session:
            repository = BuyerRepository(discovery_session)
            access_code_ids = [
                str(row.id) for row in repository.list_expired_access_codes(now=datetime.now(UTC), limit=limit)
            ]

        details: list[dict[str, str]] = []
        success_count = 0
        failed_count = 0
        for access_code_id in access_code_ids:
            with self.session_factory() as session:
                service = PlatformAdminService(
                    RuntimeSessionRepository(session),
                    BuyerRepository(session),
                    adapter_client=_NoopAdapterClient(),
                    audit_service=AuditService(session),
                )
                try:
                    code = service.expire_access_code(access_code_id)
                    session.commit()
                    success_count += 1
                    details.append(
                        {
                            "access_code_id": access_code_id,
                            "status": code.status,
                            "result": "expired",
                        }
                    )
                except ValueError as exc:
                    session.rollback()
                    failed_count += 1
                    details.append(
                        {
                            "access_code_id": access_code_id,
                            "status": "failed",
                            "detail": str(exc),
                        }
                    )

        return MaintenanceRunResponse(
            job_name="access_code_reaper",
            status="success" if failed_count == 0 else "partial_failure",
            processed_count=len(access_code_ids),
            success_count=success_count,
            failed_count=failed_count,
            details=details,
        )


@dataclass
class RuntimeSessionReaper:
    session_factory: sessionmaker[Session]
    adapter_factory: Callable[[], AdapterClient]

    def run_once(self, *, limit: int = 25, force: bool = False) -> MaintenanceRunResponse:
        with self.session_factory() as discovery_session:
            repository = RuntimeSessionRepository(discovery_session)
            session_ids = [
                str(row.id)
                for row in repository.list_expired_active_sessions(now=datetime.now(UTC), limit=limit)
            ]

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
                    runtime_session = service.expire_runtime_session(session_id, force=force)
                    session.commit()
                    success_count += 1
                    details.append(
                        {
                            "session_id": session_id,
                            "status": runtime_session.status,
                            "result": "expired",
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
            job_name="runtime_session_reaper",
            status="success" if failed_count == 0 else "partial_failure",
            processed_count=len(session_ids),
            success_count=success_count,
            failed_count=failed_count,
            details=details,
        )


class _NoopAdapterClient(AdapterClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://localhost", token="", timeout_seconds=1.0)
