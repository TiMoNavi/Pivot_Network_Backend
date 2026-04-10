from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend_app.api.deps import get_adapter_client, require_roles
from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.core.config import get_settings
from backend_app.db.models.audit import ActivityEvent
from backend_app.db.models.swarm import SwarmCluster, SwarmNode
from backend_app.db.models.user import User
from backend_app.db.session import SessionLocal, get_db_session
from backend_app.repositories.buyer_repository import BuyerRepository
from backend_app.repositories.runtime_session_repository import RuntimeSessionRepository
from backend_app.schemas.platform import (
    MaintenanceRunResponse,
    OperationLogRead,
    PlatformOrderRead,
    PlatformOverviewResponse,
    PlatformRuntimeSessionRead,
    SwarmSyncResponse,
)
from backend_app.services.audit_service import AuditService
from backend_app.services.platform_admin_service import PlatformAdminService
from backend_app.services.swarm_sync_service import SwarmSyncService
from backend_app.workers.reapers import AccessCodeReaper, RuntimeSessionReaper
from backend_app.workers.runtime_refresh import RuntimeRefreshWorker

router = APIRouter(prefix="/platform", tags=["platform"])
settings = get_settings()


def get_platform_admin_service(
    session: Session = Depends(get_db_session),
    client: AdapterClient = Depends(get_adapter_client),
) -> PlatformAdminService:
    return PlatformAdminService(
        RuntimeSessionRepository(session),
        BuyerRepository(session),
        client,
        audit_service=AuditService(session),
    )


@router.get("/overview", response_model=PlatformOverviewResponse)
def platform_overview(
    session: Session = Depends(get_db_session),
    client: AdapterClient = Depends(get_adapter_client),
    _admin=Depends(require_roles("platform_admin")),
) -> PlatformOverviewResponse:
    try:
        adapter_health = client.get_health()
    except AdapterClientError as exc:
        adapter_health = {"status": "error", "detail": exc.detail}

    counts = {
        "users": session.scalar(select(func.count()).select_from(User)) or 0,
        "nodes": session.scalar(select(func.count()).select_from(SwarmNode)) or 0,
        "clusters": session.scalar(select(func.count()).select_from(SwarmCluster)) or 0,
    }
    last_sync = session.scalar(select(func.max(SwarmCluster.last_synced_at)))

    return PlatformOverviewResponse(
        adapter_health=adapter_health,
        database="ok",
        counts=counts,
        last_sync_at=last_sync,
    )


@router.get("/swarm/overview")
def platform_swarm_overview(
    client: AdapterClient = Depends(get_adapter_client),
    _admin=Depends(require_roles("platform_admin")),
) -> dict[str, Any]:
    try:
        return client.get_swarm_overview()
    except AdapterClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})


@router.post("/swarm/sync", response_model=SwarmSyncResponse)
def platform_swarm_sync(
    session: Session = Depends(get_db_session),
    client: AdapterClient = Depends(get_adapter_client),
    _admin=Depends(require_roles("platform_admin")),
) -> SwarmSyncResponse:
    service = SwarmSyncService(session, client)
    return service.sync(sync_scope="manual")


@router.get("/nodes")
def platform_nodes(
    session: Session = Depends(get_db_session),
    _admin=Depends(require_roles("platform_admin")),
) -> list[dict[str, Any]]:
    rows = session.scalars(select(SwarmNode).order_by(SwarmNode.last_seen_at.desc().nullslast(), SwarmNode.hostname.asc()))
    return [_serialize_platform_node(node) for node in rows]


@router.get("/nodes/{node_id}")
def platform_node_detail(
    node_id: str,
    session: Session = Depends(get_db_session),
    _admin=Depends(require_roles("platform_admin")),
) -> dict[str, Any]:
    node = session.scalar(
        select(SwarmNode).where((SwarmNode.id == node_id) | (SwarmNode.swarm_node_id == node_id))
    )
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    payload = _serialize_platform_node(node)
    payload["raw_payload"] = node.raw_payload
    return payload


def _serialize_platform_node(node: SwarmNode) -> dict[str, Any]:
    raw_node = (node.raw_payload or {}).get("node") or {}
    node_addr = raw_node.get("node_addr")
    expected_wireguard_addr = settings.seller_compute_swarm_advertise_addr
    return {
        "id": str(node.id),
        "swarm_node_id": node.swarm_node_id,
        "hostname": node.hostname,
        "role": node.role,
        "status": node.status,
        "availability": node.availability,
        "platform_role": node.platform_role,
        "compute_enabled": node.compute_enabled,
        "compute_node_id": node.compute_node_id,
        "seller_user_id": node.seller_user_id,
        "accelerator": node.accelerator,
        "node_addr": node_addr,
        "expected_wireguard_addr": expected_wireguard_addr,
        "wireguard_addr_match": bool(node_addr) and node_addr == expected_wireguard_addr,
        "network_mode": settings.seller_compute_network_mode,
        "last_seen_at": node.last_seen_at,
    }


@router.get("/activity")
def platform_activity(
    session: Session = Depends(get_db_session),
    _admin=Depends(require_roles("platform_admin")),
) -> list[dict[str, Any]]:
    rows = session.scalars(select(ActivityEvent).order_by(ActivityEvent.created_at.desc()).limit(50))
    return [
        {
            "id": str(event.id),
            "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
            "actor_role": event.actor_role,
            "event_type": event.event_type,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "payload": event.payload,
            "created_at": event.created_at,
        }
        for event in rows
    ]


@router.get("/orders", response_model=list[PlatformOrderRead])
def platform_orders(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _admin=Depends(require_roles("platform_admin")),
    service: PlatformAdminService = Depends(get_platform_admin_service),
) -> list[PlatformOrderRead]:
    return service.list_orders(limit=limit, status=status)


@router.get("/runtime-sessions", response_model=list[PlatformRuntimeSessionRead])
def platform_runtime_sessions(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _admin=Depends(require_roles("platform_admin")),
    service: PlatformAdminService = Depends(get_platform_admin_service),
) -> list[PlatformRuntimeSessionRead]:
    return service.list_runtime_sessions(limit=limit, status=status)


@router.get("/runtime-sessions/{session_id}", response_model=PlatformRuntimeSessionRead)
def platform_runtime_session_detail(
    session_id: str,
    _admin=Depends(require_roles("platform_admin")),
    service: PlatformAdminService = Depends(get_platform_admin_service),
) -> PlatformRuntimeSessionRead:
    try:
        return service.get_runtime_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime-sessions/{session_id}/refresh", response_model=PlatformRuntimeSessionRead)
def platform_runtime_session_refresh(
    session_id: str,
    session: Session = Depends(get_db_session),
    _admin=Depends(require_roles("platform_admin")),
    service: PlatformAdminService = Depends(get_platform_admin_service),
) -> PlatformRuntimeSessionRead:
    try:
        response = service.refresh_runtime_session(session_id)
        session.commit()
        return response
    except AdapterClientError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/operation-logs", response_model=list[OperationLogRead])
def platform_operation_logs(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _admin=Depends(require_roles("platform_admin")),
    service: PlatformAdminService = Depends(get_platform_admin_service),
) -> list[OperationLogRead]:
    return service.list_operation_logs(limit=limit, status=status)


@router.post("/maintenance/runtime-refresh", response_model=MaintenanceRunResponse)
def platform_run_runtime_refresh_worker(
    limit: int = Query(default=25, ge=1, le=200),
    _admin=Depends(require_roles("platform_admin")),
) -> MaintenanceRunResponse:
    worker = RuntimeRefreshWorker(
        session_factory=SessionLocal,
        adapter_factory=get_adapter_client,
    )
    return worker.run_once(limit=limit)


@router.post("/maintenance/runtime-reaper", response_model=MaintenanceRunResponse)
def platform_run_runtime_reaper(
    limit: int = Query(default=25, ge=1, le=200),
    force: bool = Query(default=False),
    _admin=Depends(require_roles("platform_admin")),
) -> MaintenanceRunResponse:
    worker = RuntimeSessionReaper(
        session_factory=SessionLocal,
        adapter_factory=get_adapter_client,
    )
    return worker.run_once(limit=limit, force=force)


@router.post("/maintenance/access-code-reaper", response_model=MaintenanceRunResponse)
def platform_run_access_code_reaper(
    limit: int = Query(default=100, ge=1, le=500),
    _admin=Depends(require_roles("platform_admin")),
) -> MaintenanceRunResponse:
    worker = AccessCodeReaper(session_factory=SessionLocal)
    return worker.run_once(limit=limit)
