from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend_app.core.security import expires_after_hours, new_object_id
from backend_app.repositories.seller_onboarding_repository import SellerOnboardingRepository
from backend_app.repositories.trade_repository import TradeRepository
from backend_app.schemas.trade import (
    AccessGrantListRead,
    AccessGrantRead,
    OfferListRead,
    OfferRead,
    OrderActivationRead,
    OrderCreateRequest,
    OrderRead,
)
from backend_app.storage.memory_store import (
    AccessGrantRecord,
    InMemoryStore,
    JoinSessionRecord,
    OfferRecord,
    OrderRecord,
)


class TradeService:
    def __init__(
        self,
        store: InMemoryStore | None,
        *,
        download_root: Path,
        access_grant_ttl_hours: int = 12,
        seller_onboarding_repository: SellerOnboardingRepository | None = None,
        trade_repository: TradeRepository | None = None,
    ) -> None:
        self.store = store
        self.download_root = download_root
        self.access_grant_ttl_hours = access_grant_ttl_hours
        self.seller_onboarding_repository = seller_onboarding_repository
        self.trade_repository = trade_repository

    def list_offers(self) -> OfferListRead:
        if self.trade_repository is not None:
            items = [self._offer_read(offer) for offer in self.trade_repository.list_offers(status="listed")]
        else:
            items = [self._offer_read(offer) for offer in self.store.offers.values() if offer.status == "listed"]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return OfferListRead(items=items, total=len(items))

    def get_offer(self, offer_id: str) -> OfferRead:
        offer = self.trade_repository.get_offer(offer_id) if self.trade_repository is not None else self.store.offers.get(offer_id)
        if offer is None:
            raise ValueError("Offer not found.")
        return self._offer_read(offer)

    def create_order(self, buyer_user_id: str, payload: OrderCreateRequest) -> OrderRead:
        offer = self.trade_repository.get_offer(payload.offer_id) if self.trade_repository is not None else self.store.offers.get(payload.offer_id)
        if offer is None or offer.status != "listed":
            raise ValueError("Offer is not available.")

        now = datetime.now(UTC)
        order = OrderRecord(
            id=new_object_id("order"),
            buyer_user_id=buyer_user_id,
            offer_id=offer.id,
            status="created",
            requested_duration_minutes=payload.requested_duration_minutes,
            price_snapshot=offer.price_snapshot,
            runtime_bundle_status="placeholder_pending",
            access_grant_id=None,
            created_at=now,
            updated_at=now,
        )
        if self.trade_repository is not None:
            self.trade_repository.save_order(order)
            self.trade_repository.commit()
        else:
            self.store.orders[order.id] = order
        return self._order_read(order)

    def get_order(self, buyer_user_id: str, order_id: str, *, allow_admin: bool = False) -> OrderRead:
        order = self.trade_repository.get_order(order_id) if self.trade_repository is not None else self.store.orders.get(order_id)
        if order is None:
            raise ValueError("Order not found.")
        if not allow_admin and order.buyer_user_id != buyer_user_id:
            raise ValueError("Order not found.")
        return self._order_read(order)

    def activate_order(self, buyer_user_id: str, order_id: str, *, allow_admin: bool = False) -> OrderActivationRead:
        order = self.trade_repository.get_order(order_id) if self.trade_repository is not None else self.store.orders.get(order_id)
        if order is None:
            raise ValueError("Order not found.")
        if not allow_admin and order.buyer_user_id != buyer_user_id:
            raise ValueError("Order not found.")

        if order.access_grant_id:
            existing = (
                self.trade_repository.get_access_grant(order.access_grant_id)
                if self.trade_repository is not None
                else self.store.access_grants[order.access_grant_id]
            )
            return OrderActivationRead(
                order=self._order_read(order),
                access_grant=self._access_grant_read(existing),
            )

        grant = self._create_access_grant(order)
        order.status = "grant_issued"
        order.access_grant_id = grant.id
        order.updated_at = datetime.now(UTC)
        if self.trade_repository is not None:
            self.trade_repository.save_order(order)
            self.trade_repository.save_access_grant(grant)
            self.trade_repository.commit()
        else:
            self.store.access_grants[grant.id] = grant
        self._write_grant_download_artifact(grant)
        return OrderActivationRead(
            order=self._order_read(order),
            access_grant=self._access_grant_read(grant),
        )

    def list_active_access_grants(self, buyer_user_id: str) -> AccessGrantListRead:
        now = datetime.now(UTC)
        if self.trade_repository is not None:
            items = [self._access_grant_read(grant) for grant in self.trade_repository.list_active_access_grants(buyer_user_id, now=now)]
        else:
            items = []
            for grant in self.store.access_grants.values():
                if grant.buyer_user_id != buyer_user_id:
                    continue
                if grant.revoked_at is not None:
                    continue
                if grant.expires_at <= now:
                    continue
                if grant.status not in {"issued", "active"}:
                    continue
                items.append(self._access_grant_read(grant))

        items.sort(key=lambda item: item.issued_at, reverse=True)
        return AccessGrantListRead(items=items, total=len(items))

    def _create_access_grant(self, order: OrderRecord) -> AccessGrantRecord:
        grant_id = new_object_id("grant")
        runtime_session_id = f"placeholder-runtime-{order.id[-8:]}"
        relative_path = f"generated/access-grants/{grant_id}.json"
        offer = self.trade_repository.get_offer(order.offer_id) if self.trade_repository is not None else self.store.offers[order.offer_id]
        payload = {
            "grant_mode": "placeholder",
            "message": "Placeholder access grant. Replace with Adapter runtime inspect payload later.",
            "runtime_session_id": runtime_session_id,
            "download_relative_path": relative_path,
            "network_mode": "placeholder",
        }
        effective_target = self._resolve_effective_target_for_seller(offer.seller_user_id)
        if effective_target is not None:
            payload.update(effective_target)
            payload["grant_mode"] = "effective_target_available"
            payload["network_mode"] = "effective_target"
        now = datetime.now(UTC)
        return AccessGrantRecord(
            id=grant_id,
            buyer_user_id=order.buyer_user_id,
            order_id=order.id,
            runtime_session_id=runtime_session_id,
            status="issued",
            grant_type="placeholder",
            connect_material_payload=payload,
            issued_at=now,
            expires_at=expires_after_hours(self.access_grant_ttl_hours),
            activated_at=None,
            revoked_at=None,
        )

    def _resolve_effective_target_for_seller(self, seller_user_id: str) -> dict[str, Any] | None:
        session = self._latest_session_for_seller(seller_user_id)
        if session is None:
            return None

        if self.seller_onboarding_repository is not None:
            acceptance = self.seller_onboarding_repository.get_manager_acceptance(session.id)
            authoritative = self.seller_onboarding_repository.get_authoritative_effective_target(session.id)
            override = self.seller_onboarding_repository.get_manager_address_override(session.id)
            tcp_validation = self.seller_onboarding_repository.get_minimum_tcp_validation(session.id)
        else:
            acceptance = self.store.manager_acceptance_by_session_id.get(session.id)
            authoritative = self.store.authoritative_effective_target_by_session_id.get(session.id)
            override = self.store.manager_address_override_by_session_id.get(session.id)
            tcp_validation = self.store.minimum_tcp_validation_by_session_id.get(session.id)

        effective_target_addr: str | None = None
        effective_target_source: str | None = None
        truth_authority = "raw_manager"
        if acceptance is not None and acceptance.status == "matched" and acceptance.observed_manager_node_addr:
            effective_target_addr = acceptance.observed_manager_node_addr
            effective_target_source = "manager_matched"
        elif authoritative is not None:
            effective_target_addr = authoritative.effective_target_addr
            effective_target_source = "backend_correction"
            truth_authority = "backend_correction"
        elif override is not None:
            effective_target_addr = override.override_target_addr
            effective_target_source = "operator_override"
            truth_authority = "backend_correction"

        if effective_target_addr is None:
            return None

        minimum_tcp_validation: dict[str, Any] | None = None
        if tcp_validation is not None:
            minimum_tcp_validation = {
                "reachable": tcp_validation.reachable,
                "target_addr": tcp_validation.target_addr,
                "target_port": tcp_validation.target_port,
                "validated_against_manager_target": tcp_validation.validated_against_manager_target,
                "validated_against_effective_target": tcp_validation.validated_against_effective_target,
                "detail": tcp_validation.detail,
                "checked_at": tcp_validation.checked_at.isoformat(),
            }

            if tcp_validation.effective_target_addr:
                effective_target_addr = tcp_validation.effective_target_addr
            if tcp_validation.effective_target_source:
                effective_target_source = tcp_validation.effective_target_source
            if tcp_validation.truth_authority:
                truth_authority = tcp_validation.truth_authority

        return {
            "join_session_id": session.id,
            "join_session_status": session.status,
            "expected_wireguard_ip": session.expected_wireguard_ip,
            "effective_target_addr": effective_target_addr,
            "effective_target_source": effective_target_source,
            "truth_authority": truth_authority,
            "raw_manager_acceptance_status": None if acceptance is None else acceptance.status,
            "raw_manager_node_addr": None if acceptance is None else acceptance.observed_manager_node_addr,
            "minimum_tcp_validation": minimum_tcp_validation,
        }

    def _latest_session_for_seller(self, seller_user_id: str) -> JoinSessionRecord | None:
        if self.seller_onboarding_repository is not None:
            return self.seller_onboarding_repository.latest_session_for_seller(seller_user_id)
        sessions = [session for session in self.store.join_sessions.values() if session.seller_user_id == seller_user_id]
        if not sessions:
            return None
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return sessions[0]

    def _write_grant_download_artifact(self, grant: AccessGrantRecord) -> None:
        relative_path = str(grant.connect_material_payload.get("download_relative_path") or "").strip()
        if not relative_path:
            return

        destination = (self.download_root / relative_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "id": grant.id,
                    "buyer_user_id": grant.buyer_user_id,
                    "order_id": grant.order_id,
                    "runtime_session_id": grant.runtime_session_id,
                    "status": grant.status,
                    "grant_type": grant.grant_type,
                    "connect_material_payload": grant.connect_material_payload,
                    "issued_at": grant.issued_at.isoformat(),
                    "expires_at": grant.expires_at.isoformat(),
                },
                ensure_ascii=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _offer_read(offer: OfferRecord) -> OfferRead:
        return OfferRead(
            id=offer.id,
            title=offer.title,
            status=offer.status,
            seller_user_id=offer.seller_user_id,
            seller_node_id=offer.seller_node_id,
            compute_node_id=offer.compute_node_id,
            offer_profile_id=offer.offer_profile_id,
            runtime_image_ref=offer.runtime_image_ref,
            price_snapshot=offer.price_snapshot,
            capability_summary=offer.capability_summary,
            inventory_state=offer.inventory_state,
            published_at=offer.published_at,
            updated_at=offer.updated_at,
        )

    @staticmethod
    def _order_read(order: OrderRecord) -> OrderRead:
        return OrderRead(
            id=order.id,
            buyer_user_id=order.buyer_user_id,
            offer_id=order.offer_id,
            status=order.status,
            requested_duration_minutes=order.requested_duration_minutes,
            price_snapshot=order.price_snapshot,
            runtime_bundle_status=order.runtime_bundle_status,
            access_grant_id=order.access_grant_id,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _access_grant_read(grant: AccessGrantRecord) -> AccessGrantRead:
        return AccessGrantRead(
            id=grant.id,
            buyer_user_id=grant.buyer_user_id,
            order_id=grant.order_id,
            runtime_session_id=grant.runtime_session_id,
            status=grant.status,
            grant_type=grant.grant_type,
            connect_material_payload=grant.connect_material_payload,
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
            activated_at=grant.activated_at,
            revoked_at=grant.revoked_at,
        )
