from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.auth_trade import AccessGrantModel, OfferModel, OrderModel, SellerCapabilityAssessmentModel
from backend_app.storage.memory_store import (
    AccessGrantRecord,
    OfferRecord,
    OrderRecord,
    SellerCapabilityAssessmentRecord,
)


class TradeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def ensure_seed_offers(self) -> None:
        existing = self.session.scalar(select(OfferModel.id).limit(1))
        if existing is not None:
            return
        now = datetime.now(UTC)
        for offer in [
            OfferRecord(
                id="offer-medium-gpu",
                title="Medium GPU Runtime",
                status="listed",
                seller_user_id="seed-seller-1",
                seller_node_id="seed-node-1",
                compute_node_id="seed-node-1",
                offer_profile_id="profile-medium-gpu",
                runtime_image_ref="registry.example.com/pivot/runtime:python-gpu-v1",
                price_snapshot={"currency": "CNY", "hourly_price": 12.5},
                capability_summary={"cpu_limit": 8, "memory_limit_gb": 32, "gpu_mode": "shared"},
                inventory_state={"available": True, "reason": None},
                source_join_session_id=None,
                source_assessment_id=None,
                published_at=now,
                updated_at=now,
            ),
            OfferRecord(
                id="offer-small-cpu",
                title="Small CPU Runtime",
                status="listed",
                seller_user_id="seed-seller-2",
                seller_node_id="seed-node-2",
                compute_node_id="seed-node-2",
                offer_profile_id="profile-small-cpu",
                runtime_image_ref="registry.example.com/pivot/runtime:python-cpu-v1",
                price_snapshot={"currency": "CNY", "hourly_price": 4.0},
                capability_summary={"cpu_limit": 2, "memory_limit_gb": 8, "gpu_mode": None},
                inventory_state={"available": True, "reason": None},
                source_join_session_id=None,
                source_assessment_id=None,
                published_at=now,
                updated_at=now,
            ),
        ]:
            self.save_offer(offer)
        self.session.flush()

    def list_offers(self, *, status: str | None = None) -> list[OfferRecord]:
        statement = select(OfferModel)
        if status is not None:
            statement = statement.where(OfferModel.status == status)
        statement = statement.order_by(OfferModel.updated_at.desc())
        return [self._offer_record(model) for model in self.session.scalars(statement)]

    def get_offer(self, offer_id: str) -> OfferRecord | None:
        model = self.session.get(OfferModel, offer_id)
        if model is None:
            return None
        return self._offer_record(model)

    def get_offer_by_compute_node_id(self, compute_node_id: str) -> OfferRecord | None:
        statement = select(OfferModel).where(OfferModel.compute_node_id == compute_node_id)
        model = self.session.scalar(statement)
        if model is None:
            return None
        return self._offer_record(model)

    def save_offer(self, record: OfferRecord) -> OfferRecord:
        model = self.session.get(OfferModel, record.id)
        if model is None:
            model = OfferModel(id=record.id)
            self.session.add(model)
        model.title = record.title
        model.status = record.status
        model.seller_user_id = record.seller_user_id
        model.seller_node_id = record.seller_node_id
        model.compute_node_id = record.compute_node_id
        model.offer_profile_id = record.offer_profile_id
        model.runtime_image_ref = record.runtime_image_ref
        model.price_snapshot = dict(record.price_snapshot)
        model.capability_summary = dict(record.capability_summary)
        model.inventory_state = dict(record.inventory_state)
        model.source_join_session_id = record.source_join_session_id
        model.source_assessment_id = record.source_assessment_id
        model.published_at = self._ensure_utc_datetime(record.published_at)
        model.updated_at = self._ensure_utc_datetime(record.updated_at)
        self.session.flush()
        return self._offer_record(model)

    def get_assessment(self, assessment_id: str) -> SellerCapabilityAssessmentRecord | None:
        model = self.session.get(SellerCapabilityAssessmentModel, assessment_id)
        if model is None:
            return None
        return self._assessment_record(model)

    def save_assessment(self, record: SellerCapabilityAssessmentRecord) -> SellerCapabilityAssessmentRecord:
        model = self.session.get(SellerCapabilityAssessmentModel, record.id)
        if model is None:
            model = SellerCapabilityAssessmentModel(id=record.id)
            self.session.add(model)
        model.seller_user_id = record.seller_user_id
        model.onboarding_session_id = record.onboarding_session_id
        model.compute_node_id = record.compute_node_id
        model.node_ref = record.node_ref
        model.assessment_status = record.assessment_status
        model.requested_offer_tier = record.requested_offer_tier
        model.requested_accelerator = record.requested_accelerator
        model.request_snapshot = dict(record.request_snapshot)
        model.sources_used = dict(record.sources_used)
        model.measured_capabilities = dict(record.measured_capabilities)
        model.pricing_decision = dict(record.pricing_decision)
        model.runtime_image_validation = dict(record.runtime_image_validation)
        model.recommended_offer = dict(record.recommended_offer)
        model.warnings = list(record.warnings)
        model.apply_offer = record.apply_offer
        model.apply_result = dict(record.apply_result)
        model.created_at = self._ensure_utc_datetime(record.created_at)
        model.updated_at = self._ensure_utc_datetime(record.updated_at)
        self.session.flush()
        return self._assessment_record(model)

    def get_order(self, order_id: str) -> OrderRecord | None:
        model = self.session.get(OrderModel, order_id)
        if model is None:
            return None
        return self._order_record(model)

    def save_order(self, record: OrderRecord) -> OrderRecord:
        model = self.session.get(OrderModel, record.id)
        if model is None:
            model = OrderModel(id=record.id)
            self.session.add(model)
        model.buyer_user_id = record.buyer_user_id
        model.offer_id = record.offer_id
        model.status = record.status
        model.requested_duration_minutes = record.requested_duration_minutes
        model.price_snapshot = dict(record.price_snapshot)
        model.runtime_bundle_status = record.runtime_bundle_status
        model.access_grant_id = record.access_grant_id
        model.created_at = self._ensure_utc_datetime(record.created_at)
        model.updated_at = self._ensure_utc_datetime(record.updated_at)
        self.session.flush()
        return self._order_record(model)

    def list_orders_for_buyer(self, buyer_user_id: str) -> list[OrderRecord]:
        statement = (
            select(OrderModel)
            .where(OrderModel.buyer_user_id == buyer_user_id)
            .order_by(OrderModel.updated_at.desc())
        )
        return [self._order_record(model) for model in self.session.scalars(statement)]

    def get_access_grant(self, grant_id: str) -> AccessGrantRecord | None:
        model = self.session.get(AccessGrantModel, grant_id)
        if model is None:
            return None
        return self._grant_record(model)

    def save_access_grant(self, record: AccessGrantRecord) -> AccessGrantRecord:
        model = self.session.get(AccessGrantModel, record.id)
        if model is None:
            model = AccessGrantModel(id=record.id)
            self.session.add(model)
        model.buyer_user_id = record.buyer_user_id
        model.order_id = record.order_id
        model.runtime_session_id = record.runtime_session_id
        model.status = record.status
        model.grant_type = record.grant_type
        model.connect_material_payload = dict(record.connect_material_payload)
        model.issued_at = self._ensure_utc_datetime(record.issued_at)
        model.expires_at = self._ensure_utc_datetime(record.expires_at)
        model.activated_at = self._ensure_utc_datetime(record.activated_at)
        model.revoked_at = self._ensure_utc_datetime(record.revoked_at)
        self.session.flush()
        return self._grant_record(model)

    def list_active_access_grants(self, buyer_user_id: str, *, now: datetime) -> list[AccessGrantRecord]:
        statement = (
            select(AccessGrantModel)
            .where(
                AccessGrantModel.buyer_user_id == buyer_user_id,
                AccessGrantModel.revoked_at.is_(None),
                AccessGrantModel.expires_at > now,
                AccessGrantModel.status.in_(("issued", "active")),
            )
            .order_by(AccessGrantModel.issued_at.desc())
        )
        return [self._grant_record(model) for model in self.session.scalars(statement)]

    @staticmethod
    def _offer_record(model: OfferModel) -> OfferRecord:
        return OfferRecord(
            id=model.id,
            title=model.title,
            status=model.status,
            seller_user_id=model.seller_user_id,
            seller_node_id=model.seller_node_id,
            compute_node_id=model.compute_node_id,
            offer_profile_id=model.offer_profile_id,
            runtime_image_ref=model.runtime_image_ref,
            price_snapshot=dict(model.price_snapshot or {}),
            capability_summary=dict(model.capability_summary or {}),
            inventory_state=dict(model.inventory_state or {}),
            source_join_session_id=model.source_join_session_id,
            source_assessment_id=model.source_assessment_id,
            published_at=TradeRepository._ensure_utc_datetime(model.published_at),
            updated_at=TradeRepository._ensure_utc_datetime(model.updated_at),
        )

    @staticmethod
    def _assessment_record(model: SellerCapabilityAssessmentModel) -> SellerCapabilityAssessmentRecord:
        return SellerCapabilityAssessmentRecord(
            id=model.id,
            seller_user_id=model.seller_user_id,
            onboarding_session_id=model.onboarding_session_id,
            compute_node_id=model.compute_node_id,
            node_ref=model.node_ref,
            assessment_status=model.assessment_status,
            requested_offer_tier=model.requested_offer_tier,
            requested_accelerator=model.requested_accelerator,
            request_snapshot=dict(model.request_snapshot or {}),
            sources_used=dict(model.sources_used or {}),
            measured_capabilities=dict(model.measured_capabilities or {}),
            pricing_decision=dict(model.pricing_decision or {}),
            runtime_image_validation=dict(model.runtime_image_validation or {}),
            recommended_offer=dict(model.recommended_offer or {}),
            warnings=list(model.warnings or []),
            apply_offer=model.apply_offer,
            apply_result=dict(model.apply_result or {}),
            created_at=TradeRepository._ensure_utc_datetime(model.created_at),
            updated_at=TradeRepository._ensure_utc_datetime(model.updated_at),
        )

    @staticmethod
    def _order_record(model: OrderModel) -> OrderRecord:
        return OrderRecord(
            id=model.id,
            buyer_user_id=model.buyer_user_id,
            offer_id=model.offer_id,
            status=model.status,
            requested_duration_minutes=model.requested_duration_minutes,
            price_snapshot=dict(model.price_snapshot or {}),
            runtime_bundle_status=model.runtime_bundle_status,
            access_grant_id=model.access_grant_id,
            created_at=TradeRepository._ensure_utc_datetime(model.created_at),
            updated_at=TradeRepository._ensure_utc_datetime(model.updated_at),
        )

    @staticmethod
    def _grant_record(model: AccessGrantModel) -> AccessGrantRecord:
        return AccessGrantRecord(
            id=model.id,
            buyer_user_id=model.buyer_user_id,
            order_id=model.order_id,
            runtime_session_id=model.runtime_session_id,
            status=model.status,
            grant_type=model.grant_type,
            connect_material_payload=dict(model.connect_material_payload or {}),
            issued_at=TradeRepository._ensure_utc_datetime(model.issued_at),
            expires_at=TradeRepository._ensure_utc_datetime(model.expires_at),
            activated_at=TradeRepository._ensure_utc_datetime(model.activated_at),
            revoked_at=TradeRepository._ensure_utc_datetime(model.revoked_at),
        )

    @staticmethod
    def _ensure_utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
