from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.platform import ImageArtifact, ImageOffer, Node
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


def placement_constraint_for_node(node: Node) -> str:
    import re

    match = re.search(r"node_id=([a-z0-9]+)", node.swarm_state or "", re.IGNORECASE)
    if match:
        return f"node.id=={match.group(1)}"
    return f"node.hostname=={node.hostname}"


def merge_probe_capabilities(node: Node, probe: dict[str, object]) -> dict[str, object]:
    node_caps = node.capabilities or {}
    return {
        "cpu_logical": int(probe.get("cpu_logical") or node_caps.get("cpu_count_logical") or 0),
        "memory_total_mb": float(probe.get("memory_total_mb") or node_caps.get("memory_total_mb") or 0.0),
        "gpus": probe.get("gpus") or node_caps.get("gpus") or [],
        "node_capabilities_snapshot": node_caps,
    }


def run_offer_probe_and_pricing(
    db: Session,
    *,
    seller_user_id: int,
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

    placement_constraint = placement_constraint_for_node(node)
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
        measured = merge_probe_capabilities(node, dict(probe_result.get("probe") or {}))
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
            seller_user_id=seller_user_id,
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
