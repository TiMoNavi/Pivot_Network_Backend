from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.identity import User
from app.models.platform import BuyerOrder, ImageOffer, Node
from app.schemas.platform import BuyerOrderCreateRequest, BuyerOrderRedeemRequest, BuyerOrderRedeemResponse, BuyerOrderResponse
from app.services.activity import log_activity

router = APIRouter(prefix="/buyer")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_order(order: BuyerOrder, offer: ImageOffer | None, node: Node | None) -> BuyerOrderResponse:
    return BuyerOrderResponse(
        id=order.id,
        offer_id=order.offer_id,
        seller_node_key=node.node_key if node else "",
        repository=offer.repository if offer else "",
        tag=offer.tag if offer else "",
        runtime_image_ref=offer.runtime_image_ref if offer else "",
        requested_duration_minutes=order.requested_duration_minutes,
        issued_hourly_price_cny=order.issued_hourly_price_cny,
        order_status=order.order_status,
        license_token=order.license_token,
        license_redeemed_at=order.license_redeemed_at,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@router.post("/orders", response_model=BuyerOrderResponse)
def create_buyer_order(
    payload: BuyerOrderCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerOrderResponse:
    offer = db.get(ImageOffer, payload.offer_id)
    if offer is None or offer.offer_status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")
    node = db.get(Node, offer.node_id)
    if node is None or node.status != "available":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seller node is not available.")
    if offer.current_billable_price_cny_per_hour is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Offer price is unavailable.")

    order = BuyerOrder(
        buyer_user_id=current_user.id,
        offer_id=offer.id,
        requested_duration_minutes=payload.requested_duration_minutes,
        issued_hourly_price_cny=float(offer.current_billable_price_cny_per_hour),
        order_status="issued",
        license_token=secrets.token_urlsafe(24),
    )
    db.add(order)
    db.flush()
    log_activity(
        db,
        seller_user_id=offer.seller_user_id,
        node_id=offer.node_id,
        image_id=offer.image_artifact_id,
        event_type="buyer_order_issued",
        summary=f"Issued buyer order for {offer.repository}:{offer.tag}",
        metadata={
            "order_id": order.id,
            "buyer_user_id": current_user.id,
            "offer_id": offer.id,
            "requested_duration_minutes": payload.requested_duration_minutes,
        },
    )
    db.commit()
    db.refresh(order)
    return _serialize_order(order, offer, node)


@router.get("/orders", response_model=list[BuyerOrderResponse])
def list_buyer_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BuyerOrderResponse]:
    orders = db.scalars(select(BuyerOrder).where(BuyerOrder.buyer_user_id == current_user.id).order_by(BuyerOrder.id.desc())).all()
    offers = {
        offer.id: offer
        for offer in db.scalars(select(ImageOffer).where(ImageOffer.id.in_([order.offer_id for order in orders]))).all()
    } if orders else {}
    nodes = {
        node.id: node for node in db.scalars(select(Node).where(Node.id.in_([offer.node_id for offer in offers.values()]))).all()
    } if offers else {}
    return [_serialize_order(order, offers.get(order.offer_id), nodes.get(offers.get(order.offer_id).node_id) if offers.get(order.offer_id) else None) for order in orders]


@router.get("/orders/{order_id}", response_model=BuyerOrderResponse)
def read_buyer_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerOrderResponse:
    order = db.scalar(select(BuyerOrder).where(BuyerOrder.id == order_id, BuyerOrder.buyer_user_id == current_user.id))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    offer = db.get(ImageOffer, order.offer_id)
    node = db.get(Node, offer.node_id) if offer else None
    return _serialize_order(order, offer, node)


@router.post("/orders/redeem", response_model=BuyerOrderRedeemResponse)
def redeem_buyer_order_license(payload: BuyerOrderRedeemRequest, db: Session = Depends(get_db)) -> BuyerOrderRedeemResponse:
    order = db.scalar(select(BuyerOrder).where(BuyerOrder.license_token == payload.license_token))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License token not found.")
    if order.license_redeemed_at is None:
        order.license_redeemed_at = utcnow()
        order.order_status = "redeemed"
        db.commit()
        db.refresh(order)
    offer = db.get(ImageOffer, order.offer_id)
    node = db.get(Node, offer.node_id) if offer else None
    if offer is None or node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order offer not found.")
    return BuyerOrderRedeemResponse(
        order_id=order.id,
        offer_id=order.offer_id,
        seller_node_key=node.node_key,
        runtime_image_ref=offer.runtime_image_ref,
        requested_duration_minutes=order.requested_duration_minutes,
        issued_hourly_price_cny=order.issued_hourly_price_cny,
        order_status=order.order_status,
        license_token=order.license_token,
    )
