from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.activity import ActivityEvent
from app.models.identity import User
from app.models.platform import ImageArtifact, ImageOffer, Node
from app.schemas.activity import ActivityEventResponse
from app.schemas.platform import ImageOfferCreateRequest, ImageOfferProbeRequest, ImageOfferResponse
from app.services.image_offer_publishing import run_offer_probe_and_pricing
from app.services.pricing_engine import PricingEngineError
from app.services.swarm_manager import SwarmManagerError

router = APIRouter(prefix="/platform")
def _serialize_image_offer(offer: ImageOffer) -> ImageOfferResponse:
    return ImageOfferResponse(
        id=offer.id,
        seller_user_id=offer.seller_user_id,
        node_id=offer.node_id,
        image_artifact_id=offer.image_artifact_id,
        repository=offer.repository,
        tag=offer.tag,
        digest=offer.digest,
        runtime_image_ref=offer.runtime_image_ref,
        offer_status=offer.offer_status,
        probe_status=offer.probe_status,
        probe_measured_capabilities=offer.probe_measured_capabilities,
        pricing_error=offer.pricing_error,
        current_reference_price_cny_per_hour=offer.current_reference_price_cny_per_hour,
        current_billable_price_cny_per_hour=offer.current_billable_price_cny_per_hour,
        current_price_snapshot_id=offer.current_price_snapshot_id,
        last_probed_at=offer.last_probed_at,
        last_priced_at=offer.last_priced_at,
        pricing_stale_at=offer.pricing_stale_at,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
    )


@router.post("/image-offers", response_model=ImageOfferResponse)
def publish_image_offer(
    payload: ImageOfferCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageOfferResponse:
    image = db.scalar(
        select(ImageArtifact).where(ImageArtifact.id == payload.image_artifact_id, ImageArtifact.seller_user_id == current_user.id)
    )
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image artifact not found.")
    if image.node_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Image artifact is not bound to a node.")
    node = db.scalar(select(Node).where(Node.id == image.node_id, Node.seller_user_id == current_user.id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")

    try:
        offer = run_offer_probe_and_pricing(
            db,
            seller_user_id=current_user.id,
            image=image,
            node=node,
            timeout_seconds=settings.PRICING_PROBE_TIMEOUT_SECONDS,
        )
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PricingEngineError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return _serialize_image_offer(offer)


@router.post("/image-offers/{offer_id}/probe", response_model=ImageOfferResponse)
def reprobe_image_offer(
    offer_id: int,
    payload: ImageOfferProbeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageOfferResponse:
    offer = db.scalar(select(ImageOffer).where(ImageOffer.id == offer_id, ImageOffer.seller_user_id == current_user.id))
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image offer not found.")
    image = db.scalar(
        select(ImageArtifact).where(ImageArtifact.id == offer.image_artifact_id, ImageArtifact.seller_user_id == current_user.id)
    )
    node = db.scalar(select(Node).where(Node.id == offer.node_id, Node.seller_user_id == current_user.id))
    if image is None or node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image offer dependencies not found.")

    try:
        offer = run_offer_probe_and_pricing(
            db,
            seller_user_id=current_user.id,
            image=image,
            node=node,
            timeout_seconds=payload.timeout_seconds,
        )
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PricingEngineError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return _serialize_image_offer(offer)


@router.get("/image-offers", response_model=list[ImageOfferResponse])
def list_image_offers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ImageOfferResponse]:
    offers = db.scalars(select(ImageOffer).where(ImageOffer.seller_user_id == current_user.id).order_by(ImageOffer.id)).all()
    return [_serialize_image_offer(offer) for offer in offers]
