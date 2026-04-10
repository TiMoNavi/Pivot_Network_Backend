from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend_app.api.deps import get_adapter_client, get_db_session, require_roles
from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.repositories.buyer_repository import BuyerRepository
from backend_app.repositories.runtime_session_repository import RuntimeSessionRepository
from backend_app.schemas.buyer import (
    AccessCodeRedeemRequest,
    AccessCodeRedeemResponse,
    BuyerOrderCreateRequest,
    BuyerOrderCreateResponse,
    BuyerOrderRead,
    CatalogOfferRead,
)
from backend_app.services.audit_service import AuditService
from backend_app.services.buyer_runtime_client_service import BuyerRuntimeClientService
from backend_app.services.buyer_service import BuyerService
from backend_app.schemas.runtime_session import (
    BuyerConnectMaterialResponse,
    BuyerRuntimeClientBootstrapConfigRead,
    BuyerRuntimeClientEnvReportWrite,
    BuyerRuntimeClientSessionRead,
    BuyerRuntimeSessionCreateRequest,
    BuyerRuntimeSessionRead,
)
from backend_app.services.runtime_session_service import RuntimeSessionService

router = APIRouter(prefix="/buyer", tags=["buyer"])


def get_buyer_service(session: Session = Depends(get_db_session)) -> BuyerService:
    return BuyerService(BuyerRepository(session), audit_service=AuditService(session))


def get_runtime_session_service(
    session: Session = Depends(get_db_session),
    client: AdapterClient = Depends(get_adapter_client),
) -> RuntimeSessionService:
    return RuntimeSessionService(
        BuyerRepository(session),
        RuntimeSessionRepository(session),
        client,
        audit_service=AuditService(session),
    )


def get_buyer_runtime_client_service(
    session: Session = Depends(get_db_session),
    client: AdapterClient = Depends(get_adapter_client),
) -> BuyerRuntimeClientService:
    return BuyerRuntimeClientService(
        session,
        RuntimeSessionRepository(session),
        client,
        audit_service=AuditService(session),
    )


@router.get("/catalog/offers", response_model=list[CatalogOfferRead])
def buyer_catalog_offers(
    _buyer=Depends(require_roles("buyer", "platform_admin")),
    service: BuyerService = Depends(get_buyer_service),
) -> list[CatalogOfferRead]:
    return service.list_catalog_offers()


@router.post("/orders", response_model=BuyerOrderCreateResponse, status_code=status.HTTP_201_CREATED)
def buyer_create_order(
    payload: BuyerOrderCreateRequest,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: BuyerService = Depends(get_buyer_service),
) -> BuyerOrderCreateResponse:
    try:
        response = service.create_order(str(user.id), payload)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/orders/{order_id}", response_model=BuyerOrderRead)
def buyer_get_order(
    order_id: str,
    user=Depends(require_roles("buyer", "platform_admin")),
    service: BuyerService = Depends(get_buyer_service),
) -> BuyerOrderRead:
    try:
        return service.get_order(str(user.id), order_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/access-codes/redeem", response_model=AccessCodeRedeemResponse)
def buyer_redeem_access_code(
    payload: AccessCodeRedeemRequest,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: BuyerService = Depends(get_buyer_service),
) -> AccessCodeRedeemResponse:
    try:
        response = service.redeem_access_code(str(user.id), payload)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/runtime-sessions", response_model=BuyerRuntimeSessionRead, status_code=status.HTTP_201_CREATED)
def buyer_create_runtime_session(
    payload: BuyerRuntimeSessionCreateRequest,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: RuntimeSessionService = Depends(get_runtime_session_service),
) -> BuyerRuntimeSessionRead:
    try:
        response = service.create_session(str(user.id), payload)
        session.commit()
        return response
    except AdapterClientError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/runtime-sessions/{session_id}", response_model=BuyerRuntimeSessionRead)
def buyer_get_runtime_session(
    session_id: str,
    user=Depends(require_roles("buyer", "platform_admin")),
    service: RuntimeSessionService = Depends(get_runtime_session_service),
) -> BuyerRuntimeSessionRead:
    try:
        return service.get_buyer_session(str(user.id), session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runtime-sessions/{session_id}/connect-material", response_model=BuyerConnectMaterialResponse)
def buyer_get_connect_material(
    session_id: str,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: RuntimeSessionService = Depends(get_runtime_session_service),
) -> BuyerConnectMaterialResponse:
    try:
        response = service.get_connect_material(str(user.id), session_id)
        session.commit()
        return response
    except AdapterClientError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runtime-sessions/{session_id}/stop", response_model=BuyerRuntimeSessionRead)
def buyer_stop_runtime_session(
    session_id: str,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: RuntimeSessionService = Depends(get_runtime_session_service),
) -> BuyerRuntimeSessionRead:
    try:
        response = service.stop_session(str(user.id), session_id)
        session.commit()
        return response
    except AdapterClientError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/runtime-sessions/{session_id}/bootstrap-config", response_model=BuyerRuntimeClientBootstrapConfigRead)
def buyer_runtime_session_bootstrap_config(
    session_id: str,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: BuyerRuntimeClientService = Depends(get_buyer_runtime_client_service),
) -> BuyerRuntimeClientBootstrapConfigRead:
    try:
        response = service.get_bootstrap_config(user.id, session_id)
        session.commit()
        return response
    except AdapterClientError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/runtime-sessions/{session_id}/client-session", response_model=BuyerRuntimeClientSessionRead)
def buyer_runtime_client_session(
    session_id: str,
    user=Depends(require_roles("buyer", "platform_admin")),
    service: BuyerRuntimeClientService = Depends(get_buyer_runtime_client_service),
) -> BuyerRuntimeClientSessionRead:
    try:
        return service.get_client_session(user.id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runtime-sessions/{session_id}/env-report", response_model=BuyerRuntimeClientSessionRead)
def buyer_runtime_env_report(
    session_id: str,
    payload: BuyerRuntimeClientEnvReportWrite,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: BuyerRuntimeClientService = Depends(get_buyer_runtime_client_service),
) -> BuyerRuntimeClientSessionRead:
    try:
        response = service.report_env(user.id, session_id, payload.env_report)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runtime-sessions/{session_id}/heartbeat", response_model=BuyerRuntimeClientSessionRead)
def buyer_runtime_heartbeat(
    session_id: str,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: BuyerRuntimeClientService = Depends(get_buyer_runtime_client_service),
) -> BuyerRuntimeClientSessionRead:
    try:
        response = service.heartbeat(user.id, session_id)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runtime-sessions/{session_id}/close", response_model=BuyerRuntimeClientSessionRead)
def buyer_runtime_close(
    session_id: str,
    user=Depends(require_roles("buyer", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: BuyerRuntimeClientService = Depends(get_buyer_runtime_client_service),
) -> BuyerRuntimeClientSessionRead:
    try:
        response = service.close(user.id, session_id)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
