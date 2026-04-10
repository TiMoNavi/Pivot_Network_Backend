from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend_app.core.security import new_object_id
from backend_app.repositories.trade_repository import TradeRepository
from backend_app.storage.memory_store import OfferRecord, SellerCapabilityAssessmentRecord


class OfferCommercializationService:
    def __init__(self, trade_repository: TradeRepository) -> None:
        self.trade_repository = trade_repository

    def apply_assessment(self, assessment: SellerCapabilityAssessmentRecord) -> dict[str, Any]:
        compute_node_id = str(assessment.compute_node_id or "").strip()
        if not compute_node_id:
            return {"status": "skipped", "reason": "compute_node_id_missing"}

        now = datetime.now(UTC)
        existing = self.trade_repository.get_offer_by_compute_node_id(compute_node_id)
        recommended_offer = dict(assessment.recommended_offer or {})
        inventory_state = dict(recommended_offer.get("inventory_state") or {})
        inventory_state.setdefault("assessment_id", assessment.id)
        inventory_state.setdefault("assessment_status", assessment.assessment_status)

        publishable = assessment.assessment_status == "sellable" and bool(recommended_offer.get("publishable"))
        if publishable:
            offer_id = existing.id if existing is not None else new_object_id("offer")
            published_at = now if existing is None or existing.published_at is None else existing.published_at
            record = OfferRecord(
                id=offer_id,
                title=str(recommended_offer.get("title") or f"Compute Runtime ({compute_node_id})"),
                status="listed",
                seller_user_id=assessment.seller_user_id,
                seller_node_id=str(recommended_offer.get("seller_node_id") or compute_node_id),
                offer_profile_id=str(recommended_offer.get("offer_profile_id") or ""),
                runtime_image_ref=str(recommended_offer.get("runtime_image_ref") or ""),
                price_snapshot=dict(recommended_offer.get("price_snapshot") or {}),
                capability_summary=dict(recommended_offer.get("capability_summary") or {}),
                inventory_state=inventory_state,
                published_at=published_at,
                updated_at=now,
                compute_node_id=compute_node_id,
                source_join_session_id=assessment.onboarding_session_id,
                source_assessment_id=assessment.id,
            )
            saved = self.trade_repository.save_offer(record)
            self.trade_repository.commit()
            return {
                "status": "listed",
                "offer_id": saved.id,
                "compute_node_id": compute_node_id,
            }

        if existing is None:
            return {
                "status": "not_listed",
                "reason": "assessment_not_sellable_and_offer_missing",
                "compute_node_id": compute_node_id,
            }

        existing.status = "unavailable"
        existing.inventory_state = inventory_state
        existing.source_join_session_id = assessment.onboarding_session_id
        existing.source_assessment_id = assessment.id
        existing.updated_at = now
        saved = self.trade_repository.save_offer(existing)
        self.trade_repository.commit()
        return {
            "status": "downlisted",
            "offer_id": saved.id,
            "compute_node_id": compute_node_id,
        }
