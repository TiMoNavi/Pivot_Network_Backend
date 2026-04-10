from fastapi import APIRouter, Depends, HTTPException, status

from backend_app.api.deps import get_seller_onboarding_service
from backend_app.api.security import get_current_user
from backend_app.clients.adapter_client import AdapterClientError
from backend_app.schemas.seller_onboarding import (
    CorrectionWrite,
    ContainerRuntimeProbeWrite,
    JoinCompleteWrite,
    JoinSessionCreateRequest,
    JoinSessionRead,
    LinuxHostProbeWrite,
    LinuxSubstrateProbeWrite,
    ManagerAddressOverrideWrite,
    ManagerReverifyWrite,
    MinimumTcpValidationWrite,
)
from backend_app.services.seller_onboarding_service import SellerOnboardingService
from backend_app.storage.memory_store import UserRecord

router = APIRouter(prefix="/seller/onboarding", tags=["seller-onboarding"])


def get_seller_or_admin(user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if user.role not in {"seller", "platform_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller access required.")
    return user


def raise_onboarding_error(exc: ValueError) -> None:
    detail = str(exc)
    status_code = status.HTTP_404_NOT_FOUND if detail == "Onboarding session not found." else status.HTTP_409_CONFLICT
    raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/sessions", response_model=JoinSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: JoinSessionCreateRequest,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.create_session(user.id, payload)
    except AdapterClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail}) from exc


@router.get("/sessions/{session_id}", response_model=JoinSessionRead)
def get_session(
    session_id: str,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.get_session(user.id, session_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/linux-host-probe", response_model=JoinSessionRead)
def submit_linux_host_probe(
    session_id: str,
    payload: LinuxHostProbeWrite,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.submit_linux_host_probe(user.id, session_id, payload, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/linux-substrate-probe", response_model=JoinSessionRead)
def submit_linux_substrate_probe(
    session_id: str,
    payload: LinuxSubstrateProbeWrite,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.submit_linux_substrate_probe(
            user.id,
            session_id,
            payload,
            allow_admin=user.role == "platform_admin",
        )
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/container-runtime-probe", response_model=JoinSessionRead)
def submit_container_runtime_probe(
    session_id: str,
    payload: ContainerRuntimeProbeWrite,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.submit_container_runtime_probe(
            user.id,
            session_id,
            payload,
            allow_admin=user.role == "platform_admin",
        )
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/join-complete", response_model=JoinSessionRead)
def submit_join_complete(
    session_id: str,
    payload: JoinCompleteWrite,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.submit_join_complete(user.id, session_id, payload, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/corrections", response_model=JoinSessionRead)
def submit_correction(
    session_id: str,
    payload: CorrectionWrite,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.submit_correction(user.id, session_id, payload, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/manager-address-override", response_model=JoinSessionRead)
def submit_manager_address_override(
    session_id: str,
    payload: ManagerAddressOverrideWrite,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.submit_manager_address_override(
            user.id,
            session_id,
            payload,
            allow_admin=user.role == "platform_admin",
        )
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/re-verify", response_model=JoinSessionRead)
def reverify_manager_acceptance(
    session_id: str,
    payload: ManagerReverifyWrite,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.reverify_manager_acceptance(user.id, session_id, payload, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/minimum-tcp-validation", response_model=JoinSessionRead)
def submit_minimum_tcp_validation(
    session_id: str,
    payload: MinimumTcpValidationWrite,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.submit_minimum_tcp_validation(
            user.id,
            session_id,
            payload,
            allow_admin=user.role == "platform_admin",
        )
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/heartbeat", response_model=JoinSessionRead)
def heartbeat(
    session_id: str,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.heartbeat(user.id, session_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise_onboarding_error(exc)


@router.post("/sessions/{session_id}/close", response_model=JoinSessionRead)
def close_session(
    session_id: str,
    user: UserRecord = Depends(get_seller_or_admin),
    service: SellerOnboardingService = Depends(get_seller_onboarding_service),
) -> JoinSessionRead:
    try:
        return service.close(user.id, session_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise_onboarding_error(exc)
