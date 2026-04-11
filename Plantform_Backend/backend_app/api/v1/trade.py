from fastapi import APIRouter, Depends, HTTPException, status

from backend_app.api.deps import get_trade_service
from backend_app.api.security import get_current_user
from backend_app.schemas.trade import (
    AccessGrantRedeemByCodeRequest,
    AccessGrantRedeemRequest,
    AccessGrantListRead,
    OfferListRead,
    OfferRead,
    OrderActivationRead,
    OrderCreateRequest,
    OrderRead,
    RuntimeSessionRead,
)
from backend_app.services.trade_service import TradeService
from backend_app.storage.memory_store import UserRecord

router = APIRouter(tags=["trade"])


@router.get("/offers", response_model=OfferListRead)
def list_offers(service: TradeService = Depends(get_trade_service)) -> OfferListRead:
    return service.list_offers()


@router.get("/offers/{offer_id}", response_model=OfferRead)
def get_offer(offer_id: str, service: TradeService = Depends(get_trade_service)) -> OfferRead:
    try:
        return service.get_offer(offer_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreateRequest,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> OrderRead:
    try:
        return service.create_order(user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/orders/{order_id}", response_model=OrderRead)
def get_order(
    order_id: str,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> OrderRead:
    try:
        return service.get_order(user.id, order_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/orders/{order_id}/activate", response_model=OrderActivationRead)
def activate_order(
    order_id: str,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> OrderActivationRead:
    try:
        return service.activate_order(user.id, order_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/me/access-grants/active", response_model=AccessGrantListRead)
def active_access_grants(
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> AccessGrantListRead:
    return service.list_active_access_grants(user.id)


@router.post("/access-grants/redeem", response_model=RuntimeSessionRead)
def redeem_access_grant(
    payload: AccessGrantRedeemRequest,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> RuntimeSessionRead:
    try:
        return service.redeem_access_grant(user.id, payload, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/access-grants/redeem-by-code", response_model=RuntimeSessionRead)
def redeem_access_grant_by_code(
    payload: AccessGrantRedeemByCodeRequest,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> RuntimeSessionRead:
    try:
        return service.redeem_access_grant_by_code(user.id, payload, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/runtime-sessions/{runtime_session_id}", response_model=RuntimeSessionRead)
def get_runtime_session(
    runtime_session_id: str,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> RuntimeSessionRead:
    try:
        return service.get_runtime_session(user.id, runtime_session_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runtime-sessions/{runtime_session_id}/heartbeat", response_model=RuntimeSessionRead)
def heartbeat_runtime_session(
    runtime_session_id: str,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> RuntimeSessionRead:
    try:
        return service.heartbeat_runtime_session(user.id, runtime_session_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runtime-sessions/{runtime_session_id}/stop", response_model=RuntimeSessionRead)
def stop_runtime_session(
    runtime_session_id: str,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> RuntimeSessionRead:
    try:
        return service.stop_runtime_session(user.id, runtime_session_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/runtime-sessions/{runtime_session_id}/close", response_model=RuntimeSessionRead)
def close_runtime_session(
    runtime_session_id: str,
    user: UserRecord = Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
) -> RuntimeSessionRead:
    try:
        return service.close_runtime_session(user.id, runtime_session_id, allow_admin=user.role == "platform_admin")
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=detail) from exc
