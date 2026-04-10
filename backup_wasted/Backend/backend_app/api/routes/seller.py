from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend_app.api.deps import get_adapter_client, get_db_session, require_roles
from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.repositories.supply_repository import SupplyRepository
from backend_app.schemas.seller import (
    RuntimeBaseImageRead,
    RuntimeContractRead,
    SellerComputeReadyWrite,
    SellerNodeClaimRequest,
    SellerNodeRegisterRequest,
    SellerOnboardingBootstrapConfigRead,
    SellerOnboardingCreateRequest,
    SellerOnboardingEnvReportWrite,
    SellerOnboardingSessionRead,
    SellerUbuntuBootstrapConfigRead,
)
from backend_app.schemas.supply import ImageArtifactRead, ImageOfferRead, SellerImageReportRequest, SellerImageReportResponse
from backend_app.services.audit_service import AuditService
from backend_app.services.seller_onboarding_service import SellerOnboardingService
from backend_app.services.seller_service import SellerService

router = APIRouter(prefix="/seller", tags=["seller"])


def get_seller_service(
    client: AdapterClient = Depends(get_adapter_client),
    session: Session = Depends(get_db_session),
) -> SellerService:
    return SellerService(
        client,
        supply_repository=SupplyRepository(session),
        audit_service=AuditService(session),
    )


def get_seller_onboarding_service(
    client: AdapterClient = Depends(get_adapter_client),
    session: Session = Depends(get_db_session),
) -> SellerOnboardingService:
    return SellerOnboardingService(
        session,
        client,
        audit_service=AuditService(session),
    )


@router.get("/runtime-base-images", response_model=list[RuntimeBaseImageRead])
def seller_runtime_base_images(
    _seller=Depends(require_roles("seller", "platform_admin")),
    service: SellerService = Depends(get_seller_service),
) -> list[RuntimeBaseImageRead]:
    return [RuntimeBaseImageRead(**item) for item in service.get_runtime_base_images()]


@router.get("/runtime-contract", response_model=RuntimeContractRead)
def seller_runtime_contract(
    _seller=Depends(require_roles("seller", "platform_admin")),
    service: SellerService = Depends(get_seller_service),
) -> RuntimeContractRead:
    return RuntimeContractRead(**service.get_runtime_contract())


@router.post("/onboarding/sessions", response_model=SellerOnboardingSessionRead, status_code=status.HTTP_201_CREATED)
def create_onboarding_session(
    payload: SellerOnboardingCreateRequest,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingSessionRead:
    response = service.create_session(user.id, payload)
    session.commit()
    return response


@router.get("/onboarding/sessions/{session_id}", response_model=SellerOnboardingSessionRead)
def get_onboarding_session(
    session_id: str,
    user=Depends(require_roles("seller", "platform_admin")),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingSessionRead:
    try:
        return service.get_session(user.id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/onboarding/sessions/{session_id}/bootstrap-config",
    response_model=SellerOnboardingBootstrapConfigRead,
)
def get_onboarding_bootstrap_config(
    session_id: str,
    user=Depends(require_roles("seller", "platform_admin")),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingBootstrapConfigRead:
    try:
        return service.get_bootstrap_config(user.id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get(
    "/onboarding/sessions/{session_id}/ubuntu-bootstrap",
    response_model=SellerUbuntuBootstrapConfigRead,
)
def get_onboarding_ubuntu_bootstrap(
    session_id: str,
    user=Depends(require_roles("seller", "platform_admin")),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerUbuntuBootstrapConfigRead:
    try:
        return service.get_ubuntu_bootstrap(user.id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/onboarding/sessions/{session_id}/env-report", response_model=SellerOnboardingSessionRead)
def post_onboarding_env_report(
    session_id: str,
    payload: SellerOnboardingEnvReportWrite,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingSessionRead:
    try:
        response = service.update_env_report(user.id, session_id, payload.env_report)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/onboarding/sessions/{session_id}/host-env-report", response_model=SellerOnboardingSessionRead)
def post_host_env_report(
    session_id: str,
    payload: SellerOnboardingEnvReportWrite,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingSessionRead:
    try:
        response = service.update_host_env_report(user.id, session_id, payload.env_report)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/onboarding/sessions/{session_id}/ubuntu-env-report", response_model=SellerOnboardingSessionRead)
def post_ubuntu_env_report(
    session_id: str,
    payload: SellerOnboardingEnvReportWrite,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingSessionRead:
    try:
        response = service.update_ubuntu_env_report(user.id, session_id, payload.env_report)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/onboarding/sessions/{session_id}/compute-ready", response_model=SellerOnboardingSessionRead)
def post_compute_ready(
    session_id: str,
    payload: SellerComputeReadyWrite,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingSessionRead:
    try:
        response = service.mark_compute_ready(user.id, session_id, payload.detail)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/onboarding/sessions/{session_id}/heartbeat", response_model=SellerOnboardingSessionRead)
def heartbeat_onboarding_session(
    session_id: str,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingSessionRead:
    try:
        response = service.heartbeat(user.id, session_id)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/onboarding/sessions/{session_id}/close", response_model=SellerOnboardingSessionRead)
def close_onboarding_session(
    session_id: str,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> SellerOnboardingSessionRead:
    try:
        response = service.close(user.id, session_id)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/nodes/register")
def seller_register_node(
    payload: SellerNodeRegisterRequest,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerService = Depends(get_seller_service),
):
    audit = AuditService(session)
    try:
        response = service.register_node(
            seller_user_id=str(user.id),
            requested_accelerator=payload.requested_accelerator,
            requested_compute_node_id=payload.requested_compute_node_id,
        )
        audit.log_activity(
            actor_user_id=user.id,
            actor_role=user.role,
            event_type="seller_node_register_requested",
            target_type="seller_node",
            target_id=payload.requested_compute_node_id or "auto",
            payload=response,
        )
        session.commit()
        return response
    except AdapterClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})


@router.get("/nodes")
def seller_nodes(
    user=Depends(require_roles("seller", "platform_admin")),
    service: SellerService = Depends(get_seller_service),
):
    return service.list_nodes(str(user.id))


@router.get("/nodes/{node_id}")
def seller_node_detail(
    node_id: str,
    user=Depends(require_roles("seller", "platform_admin")),
    service: SellerService = Depends(get_seller_service),
):
    try:
        return service.get_node(str(user.id), node_id)
    except AdapterClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/nodes/{node_id}/claim-status")
def seller_claim_status(
    node_id: str,
    user=Depends(require_roles("seller", "platform_admin")),
    service: SellerService = Depends(get_seller_service),
):
    try:
        return service.get_claim_status(str(user.id), node_id)
    except AdapterClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post("/nodes/{node_id}/claim")
def seller_claim_node(
    node_id: str,
    payload: SellerNodeClaimRequest,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
):
    try:
        response = service.claim_node(user.id, node_id, payload)
        session.commit()
        return response
    except AdapterClientError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/images/report", response_model=SellerImageReportResponse)
def seller_report_image(
    payload: SellerImageReportRequest,
    user=Depends(require_roles("seller", "platform_admin")),
    session: Session = Depends(get_db_session),
    service: SellerService = Depends(get_seller_service),
):
    try:
        response = service.report_image(str(user.id), payload)
        session.commit()
        return response
    except AdapterClientError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"detail": "seller_image_report_failed", "error": str(exc)},
        ) from exc


@router.get("/images", response_model=list[ImageArtifactRead])
def seller_images(
    user=Depends(require_roles("seller", "platform_admin")),
    service: SellerService = Depends(get_seller_service),
) -> list[ImageArtifactRead]:
    return service.list_images(str(user.id))


@router.get("/offers", response_model=list[ImageOfferRead])
def seller_offers(
    user=Depends(require_roles("seller", "platform_admin")),
    service: SellerService = Depends(get_seller_service),
) -> list[ImageOfferRead]:
    return service.list_offers(str(user.id))
