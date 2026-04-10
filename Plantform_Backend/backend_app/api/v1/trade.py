from fastapi import APIRouter, Depends, HTTPException, status

from backend_app.api.deps import get_trade_service
from backend_app.api.security import get_current_user
from backend_app.schemas.trade import (
    AccessGrantListRead,
    OfferListRead,
    OfferRead,
    OrderActivationRead,
    OrderCreateRequest,
    OrderRead,
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
