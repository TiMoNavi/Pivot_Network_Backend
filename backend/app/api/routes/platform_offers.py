from __future__ import annotations

from datetime import datetime

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
from app.services.activity import log_activity
from app.services.pricing_engine import (
    PricingEngineError,
    build_runtime_image_ref,
    ensure_current_rate_card,
    get_or_create_image_offer_stub,
    price_image_offer,
    publish_or_update_image_offer,
)
from app.services.swarm_manager import (
    SwarmManagerError,
    probe_node_capabilities_on_node,
    validate_runtime_image_on_node,
)

router = APIRouter(prefix="/platform")


def utcnow() -> datetime:
    return datetime.utcnow()


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


def _placement_constraint_for_node(node: Node) -> str:
    import re

    match = re.search(r"node_id=([a-z0-9]+)", node.swarm_state or "", re.IGNORECASE)
    if match:
        return f"node.id=={match.group(1)}"
    return f"node.hostname=={node.hostname}"


def _merge_probe_capabilities(node: Node, probe: dict[str, object]) -> dict[str, object]:
    node_caps = node.capabilities or {}
    return {
        "cpu_logical": int(probe.get("cpu_logical") or node_caps.get("cpu_count_logical") or 0),
        "memory_total_mb": float(probe.get("memory_total_mb") or node_caps.get("memory_total_mb") or 0.0),
        "gpus": probe.get("gpus") or node_caps.get("gpus") or [],
        "node_capabilities_snapshot": node_caps,
    }


def _run_offer_probe_and_pricing(
    db: Session,
    *,
    current_user: User,
    image: ImageArtifact,
    node: Node,
    timeout_seconds: int,
) -> ImageOffer:
    offer = get_or_create_image_offer_stub(db, image_artifact=image, node=node)
    offer.offer_status = "probing"
    offer.probe_status = "running"
    offer.pricing_error = None
    db.commit()
    db.refresh(offer)

    placement_constraint = _placement_constraint_for_node(node)
    validate_service_name = f"image-validate-{offer.id}"
    probe_service_name = f"pricing-probe-{offer.id}"

    try:
        validate_runtime_image_on_node(
            settings,
            service_name=validate_service_name,
            placement_constraint=placement_constraint,
            runtime_image=build_runtime_image_ref(image),
            timeout_seconds=min(timeout_seconds, 120),
        )
        probe_result = probe_node_capabilities_on_node(
            settings,
            service_name=probe_service_name,
            placement_constraint=placement_constraint,
            probe_image=settings.PRICING_PROBE_IMAGE,
            timeout_seconds=timeout_seconds,
        )
        measured = _merge_probe_capabilities(node, dict(probe_result.get("probe") or {}))
        offer = publish_or_update_image_offer(
            db,
            image_artifact=image,
            node=node,
            probe_measured_capabilities=measured,
        )
        rate_card = ensure_current_rate_card(db)
        if rate_card is None:
            raise PricingEngineError("resource_rate_card_unavailable")
        offer = price_image_offer(db, offer, rate_card)
        log_activity(
            db,
            seller_user_id=current_user.id,
            node_id=node.id,
            image_id=image.id,
            event_type="image_offer_published",
            summary=f"Published image offer {image.repository}:{image.tag}",
            metadata={"offer_id": offer.id, "price_cny_per_hour": offer.current_billable_price_cny_per_hour},
        )
        db.commit()
        db.refresh(offer)
        return offer
    except (SwarmManagerError, PricingEngineError) as exc:
        offer.offer_status = "probe_failed"
        offer.probe_status = "failed"
        offer.pricing_error = str(exc)
        db.commit()
        raise


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
        offer = _run_offer_probe_and_pricing(
            db,
            current_user=current_user,
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
        offer = _run_offer_probe_and_pricing(
            db,
            current_user=current_user,
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
