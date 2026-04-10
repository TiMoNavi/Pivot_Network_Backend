from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from backend_app.repositories.buyer_repository import BuyerRepository
from backend_app.schemas.buyer import (
    AccessCodeRead,
    AccessCodeRedeemRequest,
    AccessCodeRedeemResponse,
    BuyerOrderCreateRequest,
    BuyerOrderCreateResponse,
    BuyerOrderRead,
    CatalogOfferRead,
)
from backend_app.services.audit_service import AuditService


class BuyerService:
    def __init__(self, repository: BuyerRepository, audit_service: AuditService | None = None) -> None:
        self.repository = repository
        self.audit = audit_service

    def list_catalog_offers(self) -> list[CatalogOfferRead]:
        offers = self.repository.list_ready_offers()
        return [
            CatalogOfferRead(
                id=str(offer.id),
                seller_user_id=offer.seller_user_id,
                swarm_node_id=offer.swarm_node_id,
                runtime_image_ref=offer.runtime_image_ref,
                offer_status=offer.offer_status,
                current_billable_price=float(offer.current_billable_price) if offer.current_billable_price is not None else None,
                probe_measured_capabilities=offer.probe_measured_capabilities,
                validation_status=offer.validation_status,
                shell_agent_status=offer.shell_agent_status,
            )
            for offer in offers
        ]

    def create_order(self, buyer_user_id: str, payload: BuyerOrderCreateRequest) -> BuyerOrderCreateResponse:
        offer = self.repository.get_offer(payload.offer_id)
        if offer is None or offer.offer_status != "offer_ready":
            raise ValueError("Offer is not available.")

        order = self.repository.create_order(
            buyer_user_id=buyer_user_id,
            offer_id=offer.id,
            order_no=self._generate_order_no(),
            order_status="access_code_issued",
            issued_hourly_price=offer.current_billable_price,
            requested_duration_minutes=payload.requested_duration_minutes,
        )
        issued_at = datetime.now(UTC)
        access_code = self.repository.create_access_code(
            order_id=order.id,
            buyer_user_id=buyer_user_id,
            access_code=self._generate_access_code(),
            status="issued",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(minutes=30),
            detail={"offer_id": str(offer.id)},
        )

        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=buyer_user_id,
                actor_role="buyer",
                event_type="buyer_order_created",
                target_type="buyer_order",
                target_id=str(order.id),
                payload={"offer_id": str(offer.id), "access_code_id": str(access_code.id)},
            )

        return BuyerOrderCreateResponse(
            order=self._order_read(order),
            access_code=self._access_code_read(access_code),
        )

    def get_order(self, buyer_user_id: str, order_id: str) -> BuyerOrderRead:
        order = self.repository.get_order(order_id, buyer_user_id)
        if order is None:
            raise ValueError("Order not found.")
        return self._order_read(order)

    def redeem_access_code(self, buyer_user_id: str, payload: AccessCodeRedeemRequest) -> AccessCodeRedeemResponse:
        access_code = self.repository.get_access_code(payload.access_code, buyer_user_id)
        if access_code is None:
            raise ValueError("Access code not found.")
        if access_code.status != "issued":
            raise ValueError("Access code is not redeemable.")
        if access_code.expires_at <= datetime.now(UTC):
            access_code.status = "expired"
            self.repository.session.add(access_code)
            self.repository.session.flush()
            raise ValueError("Access code is expired.")

        access_code.status = "redeemed"
        access_code.redeemed_at = datetime.now(UTC)
        self.repository.session.add(access_code)

        order = self.repository.get_order(access_code.order_id, buyer_user_id)
        if order is None:
            raise ValueError("Order not found.")
        order.order_status = "access_code_redeemed"
        self.repository.session.add(order)
        self.repository.session.flush()

        if self.audit is not None:
            self.audit.log_activity(
                actor_user_id=buyer_user_id,
                actor_role="buyer",
                event_type="buyer_access_code_redeemed",
                target_type="access_code",
                target_id=str(access_code.id),
                payload={"order_id": str(order.id)},
            )

        return AccessCodeRedeemResponse(
            access_code=self._access_code_read(access_code),
            can_create_runtime_session=True,
            order=self._order_read(order),
        )

    @staticmethod
    def _generate_order_no() -> str:
        return f"ORD-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"

    @staticmethod
    def _generate_access_code() -> str:
        return secrets.token_urlsafe(12)

    @staticmethod
    def _order_read(order) -> BuyerOrderRead:
        return BuyerOrderRead(
            id=str(order.id),
            buyer_user_id=str(order.buyer_user_id),
            offer_id=str(order.offer_id),
            order_no=order.order_no,
            order_status=order.order_status,
            issued_hourly_price=float(order.issued_hourly_price) if order.issued_hourly_price is not None else None,
            requested_duration_minutes=order.requested_duration_minutes,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _access_code_read(access_code) -> AccessCodeRead:
        return AccessCodeRead(
            id=str(access_code.id),
            order_id=str(access_code.order_id),
            buyer_user_id=str(access_code.buyer_user_id),
            access_code=access_code.access_code,
            status=access_code.status,
            issued_at=access_code.issued_at,
            expires_at=access_code.expires_at,
            redeemed_at=access_code.redeemed_at,
            revoked_at=access_code.revoked_at,
            detail=access_code.detail,
        )
