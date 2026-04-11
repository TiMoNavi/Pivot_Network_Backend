from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend_app.clients.adapter_client import AdapterClient, AdapterClientError
from backend_app.core.security import expires_after_hours, new_access_token, new_object_id
from backend_app.repositories.seller_onboarding_repository import SellerOnboardingRepository
from backend_app.repositories.trade_repository import TradeRepository
from backend_app.schemas.trade import (
    AccessGrantRedeemByCodeRequest,
    AccessGrantRedeemRequest,
    AccessGrantListRead,
    AccessGrantRead,
    OfferListRead,
    OfferRead,
    OrderActivationRead,
    OrderCreateRequest,
    OrderRead,
    RuntimeSessionRead,
)
from backend_app.storage.memory_store import (
    AccessGrantRecord,
    InMemoryStore,
    JoinSessionRecord,
    OfferRecord,
    OrderRecord,
    RuntimeSessionRecord,
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
        adapter_client: AdapterClient | None = None,
    ) -> None:
        self.store = store
        self.download_root = download_root
        self.access_grant_ttl_hours = access_grant_ttl_hours
        self.seller_onboarding_repository = seller_onboarding_repository
        self.trade_repository = trade_repository
        self.adapter_client = adapter_client

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
            existing = self._ensure_grant_payload_fields(existing)
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
            items = [
                self._access_grant_read(self._ensure_grant_payload_fields(grant))
                for grant in self.trade_repository.list_active_access_grants(buyer_user_id, now=now)
            ]
        else:
            items = []
            for grant in self.store.access_grants.values():
                if grant.buyer_user_id != buyer_user_id:
                    continue
                if grant.revoked_at is not None:
                    continue
                if grant.expires_at <= now:
                    continue
                if grant.status not in {"issued", "active", "redeemed"}:
                    continue
                items.append(self._access_grant_read(self._ensure_grant_payload_fields(grant)))

        items.sort(key=lambda item: item.issued_at, reverse=True)
        return AccessGrantListRead(items=items, total=len(items))

    def redeem_access_grant(
        self,
        buyer_user_id: str,
        payload: AccessGrantRedeemRequest,
        *,
        allow_admin: bool = False,
    ) -> RuntimeSessionRead:
        grant = self._grant_for_redeem_by_id(payload.grant_id, buyer_user_id, allow_admin=allow_admin)
        return self._redeem_grant(
            grant=grant,
            buyer_user_id=buyer_user_id,
            wireguard_public_key=payload.wireguard_public_key,
            network_mode=payload.network_mode,
            allow_admin=allow_admin,
        )

    def redeem_access_grant_by_code(
        self,
        buyer_user_id: str,
        payload: AccessGrantRedeemByCodeRequest,
        *,
        allow_admin: bool = False,
    ) -> RuntimeSessionRead:
        grant = self._grant_for_redeem_by_code(payload.grant_code, buyer_user_id, allow_admin=allow_admin)
        return self._redeem_grant(
            grant=grant,
            buyer_user_id=buyer_user_id,
            wireguard_public_key=payload.wireguard_public_key,
            network_mode=payload.network_mode,
            allow_admin=allow_admin,
        )

    def get_runtime_session(self, buyer_user_id: str, runtime_session_id: str, *, allow_admin: bool = False) -> RuntimeSessionRead:
        session = self._get_runtime_session_record(runtime_session_id)
        if session is None:
            raise ValueError("Runtime session not found.")
        if not allow_admin and session.buyer_user_id != buyer_user_id:
            raise ValueError("Runtime session not found.")
        session = self._refresh_runtime_session_truth(session)
        return self._runtime_session_read(session)

    def heartbeat_runtime_session(self, buyer_user_id: str, runtime_session_id: str, *, allow_admin: bool = False) -> RuntimeSessionRead:
        session = self._get_runtime_session_record(runtime_session_id)
        if session is None:
            raise ValueError("Runtime session not found.")
        if not allow_admin and session.buyer_user_id != buyer_user_id:
            raise ValueError("Runtime session not found.")
        session.last_heartbeat_at = datetime.now(UTC)
        session.updated_at = session.last_heartbeat_at
        session = self._refresh_runtime_session_truth(session)
        self._persist_runtime_session_only(session)
        return self._runtime_session_read(session)

    def stop_runtime_session(self, buyer_user_id: str, runtime_session_id: str, *, allow_admin: bool = False) -> RuntimeSessionRead:
        return self._close_or_stop_runtime_session(buyer_user_id, runtime_session_id, allow_admin=allow_admin, close_mode="stop")

    def close_runtime_session(self, buyer_user_id: str, runtime_session_id: str, *, allow_admin: bool = False) -> RuntimeSessionRead:
        return self._close_or_stop_runtime_session(buyer_user_id, runtime_session_id, allow_admin=allow_admin, close_mode="close")

    def _create_access_grant(self, order: OrderRecord) -> AccessGrantRecord:
        grant_id = new_object_id("grant")
        grant_code = new_access_token()
        expires_at = expires_after_hours(self.access_grant_ttl_hours)
        runtime_session_id = f"placeholder-runtime-{order.id[-8:]}"
        relative_path = f"generated/access-grants/{grant_id}.json"
        offer = self.trade_repository.get_offer(order.offer_id) if self.trade_repository is not None else self.store.offers[order.offer_id]
        payload = {
            "grant_id": grant_id,
            "grant_code": grant_code,
            "expires_at": self._isoformat_utc(expires_at),
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
            expires_at=expires_at,
            activated_at=None,
            revoked_at=None,
        )

    def _grant_for_redeem_by_id(self, grant_id: str, buyer_user_id: str, *, allow_admin: bool) -> AccessGrantRecord:
        grant = self.trade_repository.get_access_grant(grant_id) if self.trade_repository is not None else self.store.access_grants.get(grant_id)
        if grant is None:
            raise ValueError("Access grant not found.")
        if not allow_admin and grant.buyer_user_id != buyer_user_id:
            raise ValueError("Access grant not found.")
        return grant

    def _grant_for_redeem_by_code(self, grant_code: str, buyer_user_id: str, *, allow_admin: bool) -> AccessGrantRecord:
        if self.trade_repository is not None:
            grant = self.trade_repository.get_access_grant_by_code(grant_code)
        else:
            grant = next(
                (
                    item
                    for item in self.store.access_grants.values()
                    if str(item.connect_material_payload.get("grant_code") or "") == grant_code
                ),
                None,
            )
        if grant is None:
            raise ValueError("Access grant not found.")
        if not allow_admin and grant.buyer_user_id != buyer_user_id:
            raise ValueError("Access grant not found.")
        return grant

    def _redeem_grant(
        self,
        *,
        grant: AccessGrantRecord,
        buyer_user_id: str,
        wireguard_public_key: str,
        network_mode: str,
        allow_admin: bool,
    ) -> RuntimeSessionRead:
        del buyer_user_id
        if self.adapter_client is None:
            raise ValueError("Runtime redeem is not available.")
        if grant.revoked_at is not None:
            raise ValueError("Access grant is not available.")
        if grant.expires_at <= datetime.now(UTC):
            raise ValueError("Access grant is expired.")

        existing = None
        if grant.runtime_session_id:
            existing = self._get_runtime_session_record(grant.runtime_session_id)
        if existing is None:
            existing = self._get_runtime_session_by_grant_id(grant.id)
        if existing is not None:
            refreshed = self._refresh_runtime_session_truth(existing)
            if refreshed.status not in {"failed", "closed"}:
                if (
                    refreshed.buyer_wireguard_public_key != wireguard_public_key
                    or refreshed.network_mode != network_mode
                ):
                    session = self._reprovision_runtime_session(
                        existing=refreshed,
                        grant=grant,
                        wireguard_public_key=wireguard_public_key,
                        network_mode=network_mode,
                    )
                    return self._runtime_session_read(session)
                return self._runtime_session_read(refreshed)
            session = self._reprovision_runtime_session(
                existing=refreshed,
                grant=grant,
                wireguard_public_key=wireguard_public_key,
                network_mode=network_mode,
            )
            return self._runtime_session_read(session)

        order = self.trade_repository.get_order(grant.order_id) if self.trade_repository is not None else self.store.orders.get(grant.order_id)
        if order is None:
            raise ValueError("Order not found.")
        offer = self.trade_repository.get_offer(order.offer_id) if self.trade_repository is not None else self.store.offers.get(order.offer_id)
        if offer is None:
            raise ValueError("Offer not found.")

        session = self._provision_runtime_session(
            runtime_session_id=new_object_id("runtime_session"),
            grant=grant,
            order=order,
            offer=offer,
            wireguard_public_key=wireguard_public_key,
            network_mode=network_mode,
        )
        return self._runtime_session_read(session)

    def _provision_runtime_session(
        self,
        *,
        runtime_session_id: str,
        grant: AccessGrantRecord,
        order: OrderRecord,
        offer: OfferRecord,
        wireguard_public_key: str,
        network_mode: str,
    ) -> RuntimeSessionRecord:
        create_payload = {
            "session_id": runtime_session_id,
            "offer_id": offer.id,
            "compute_node_id": offer.compute_node_id,
            "runtime_image_ref": offer.runtime_image_ref,
            "requested_duration_minutes": order.requested_duration_minutes,
            "buyer_user_id": grant.buyer_user_id,
            "network_mode": network_mode,
            "buyer_network": {
                "public_key": wireguard_public_key,
            },
        }

        bundle_result = self._create_or_inspect_runtime_bundle(runtime_session_id, create_payload)

        now = datetime.now(UTC)
        session = RuntimeSessionRecord(
            id=runtime_session_id,
            access_grant_id=grant.id,
            order_id=order.id,
            offer_id=offer.id,
            buyer_user_id=grant.buyer_user_id,
            seller_user_id=offer.seller_user_id,
            compute_node_id=offer.compute_node_id,
            source_join_session_id=offer.source_join_session_id,
            status=self._runtime_session_status(str(bundle_result.get("status") or "")),
            runtime_bundle_status=str(bundle_result.get("status") or ""),
            network_mode=network_mode,
            buyer_wireguard_public_key=wireguard_public_key,
            runtime_service_name=self._optional_str(bundle_result.get("runtime_service_name")),
            gateway_service_name=self._optional_str(bundle_result.get("gateway_service_name")),
            network_name=self._optional_str(bundle_result.get("network_name")),
            connect_metadata=self._session_connect_metadata(dict(bundle_result.get("connect_metadata") or {})),
            wireguard_lease_metadata=dict(bundle_result.get("wireguard_lease_metadata") or {}),
            recent_error_summary=list(bundle_result.get("recent_error_summary") or []),
            created_at=now,
            updated_at=now,
            expires_at=grant.expires_at,
            last_heartbeat_at=now,
            closed_at=None,
        )

        self._persist_runtime_session_chain(session=session, grant=grant, order=order, when=now)
        return session

    def _reprovision_runtime_session(
        self,
        *,
        existing: RuntimeSessionRecord,
        grant: AccessGrantRecord,
        wireguard_public_key: str,
        network_mode: str,
    ) -> RuntimeSessionRecord:
        if self.adapter_client is None:
            raise ValueError("Runtime redeem is not available.")
        order = self.trade_repository.get_order(grant.order_id) if self.trade_repository is not None else self.store.orders.get(grant.order_id)
        if order is None:
            raise ValueError("Order not found.")
        offer = self.trade_repository.get_offer(order.offer_id) if self.trade_repository is not None else self.store.offers.get(order.offer_id)
        if offer is None:
            raise ValueError("Offer not found.")
        try:
            self.adapter_client.remove_runtime_session_bundle({"session_id": existing.id, "force": True})
        except AdapterClientError:
            pass
        return self._provision_runtime_session(
            runtime_session_id=existing.id,
            grant=grant,
            order=order,
            offer=offer,
            wireguard_public_key=wireguard_public_key,
            network_mode=network_mode,
        )

    def _create_or_inspect_runtime_bundle(self, runtime_session_id: str, create_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            create_result = self.adapter_client.create_runtime_session_bundle(create_payload)
            inspect_result = self.adapter_client.inspect_runtime_session_bundle({"session_id": runtime_session_id})
            return inspect_result or create_result
        except AdapterClientError as exc:
            raise ValueError(f"Runtime session redeem failed: {exc.detail}") from exc

    def _persist_runtime_session_chain(
        self,
        *,
        session: RuntimeSessionRecord,
        grant: AccessGrantRecord,
        order: OrderRecord,
        when: datetime,
    ) -> None:
        grant.status = "redeemed"
        grant.runtime_session_id = session.id
        grant.connect_material_payload = self._grant_payload_with_runtime_session(
            grant.connect_material_payload,
            session=session,
        )
        order.status = "session_active"
        order.runtime_bundle_status = session.runtime_bundle_status
        order.updated_at = when

        if self.trade_repository is not None:
            self.trade_repository.save_runtime_session(session)
            self.trade_repository.save_access_grant(grant)
            self.trade_repository.save_order(order)
            self.trade_repository.commit()
        else:
            self.store.runtime_sessions[session.id] = session
            self.store.access_grants[grant.id] = grant
            self.store.orders[order.id] = order

    def _persist_runtime_session_only(self, session: RuntimeSessionRecord) -> None:
        if self.trade_repository is not None:
            self.trade_repository.save_runtime_session(session)
            self.trade_repository.commit()
        else:
            self.store.runtime_sessions[session.id] = session

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

    def _get_runtime_session_record(self, runtime_session_id: str) -> RuntimeSessionRecord | None:
        if self.trade_repository is not None:
            return self.trade_repository.get_runtime_session(runtime_session_id)
        return self.store.runtime_sessions.get(runtime_session_id)

    def _get_runtime_session_by_grant_id(self, access_grant_id: str) -> RuntimeSessionRecord | None:
        if self.trade_repository is not None:
            return self.trade_repository.get_runtime_session_by_access_grant_id(access_grant_id)
        for session in self.store.runtime_sessions.values():
            if session.access_grant_id == access_grant_id:
                return session
        return None

    def _refresh_runtime_session_truth(self, session: RuntimeSessionRecord) -> RuntimeSessionRecord:
        if self.adapter_client is None or session.closed_at is not None:
            return session
        try:
            bundle_result = self.adapter_client.inspect_runtime_session_bundle({"session_id": session.id})
        except AdapterClientError:
            return session

        session.runtime_bundle_status = str(bundle_result.get("status") or session.runtime_bundle_status)
        session.status = self._runtime_session_status(session.runtime_bundle_status)
        session.runtime_service_name = self._optional_str(bundle_result.get("runtime_service_name")) or session.runtime_service_name
        session.gateway_service_name = self._optional_str(bundle_result.get("gateway_service_name")) or session.gateway_service_name
        session.network_name = self._optional_str(bundle_result.get("network_name")) or session.network_name
        session.connect_metadata = self._session_connect_metadata(dict(bundle_result.get("connect_metadata") or session.connect_metadata))
        session.wireguard_lease_metadata = dict(bundle_result.get("wireguard_lease_metadata") or session.wireguard_lease_metadata)
        session.recent_error_summary = list(bundle_result.get("recent_error_summary") or session.recent_error_summary)
        session.updated_at = datetime.now(UTC)
        self._sync_grant_and_order_from_runtime_session(session)
        self._persist_runtime_session_only(session)
        return session

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
                    "issued_at": TradeService._isoformat_utc(grant.issued_at),
                    "expires_at": TradeService._isoformat_utc(grant.expires_at),
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
        payload = dict(grant.connect_material_payload)
        return AccessGrantRead(
            id=grant.id,
            grant_id=grant.id,
            grant_code=str(payload.get("grant_code") or ""),
            buyer_user_id=grant.buyer_user_id,
            order_id=grant.order_id,
            runtime_session_id=grant.runtime_session_id,
            status=grant.status,
            grant_type=grant.grant_type,
            connect_material_payload=payload,
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
            activated_at=grant.activated_at,
            revoked_at=grant.revoked_at,
        )

    @staticmethod
    def _runtime_session_read(session: RuntimeSessionRecord) -> RuntimeSessionRead:
        return RuntimeSessionRead(
            id=session.id,
            access_grant_id=session.access_grant_id,
            order_id=session.order_id,
            offer_id=session.offer_id,
            buyer_user_id=session.buyer_user_id,
            seller_user_id=session.seller_user_id,
            compute_node_id=session.compute_node_id,
            source_join_session_id=session.source_join_session_id,
            status=session.status,
            runtime_bundle_status=session.runtime_bundle_status,
            network_mode=session.network_mode,
            runtime_service_name=session.runtime_service_name,
            gateway_service_name=session.gateway_service_name,
            network_name=session.network_name,
            connect_metadata=session.connect_metadata,
            wireguard_lease_metadata=session.wireguard_lease_metadata,
            recent_error_summary=session.recent_error_summary,
            expires_at=session.expires_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_heartbeat_at=session.last_heartbeat_at,
            closed_at=session.closed_at,
        )

    @staticmethod
    def _isoformat_utc(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _ensure_grant_payload_fields(self, grant: AccessGrantRecord) -> AccessGrantRecord:
        payload = dict(grant.connect_material_payload or {})
        changed = False

        if not payload.get("grant_id"):
            payload["grant_id"] = grant.id
            changed = True
        if not payload.get("grant_code"):
            payload["grant_code"] = new_access_token()
            changed = True
        if not payload.get("expires_at"):
            payload["expires_at"] = self._isoformat_utc(grant.expires_at)
            changed = True

        session = None
        if grant.runtime_session_id:
            session = self._get_runtime_session_record(grant.runtime_session_id)
            if session is not None:
                session = self._refresh_runtime_session_truth(session)
        if session is not None:
            enriched_payload = self._grant_payload_with_runtime_session(payload, session=session)
            if enriched_payload != payload:
                payload = enriched_payload
                changed = True

        if not changed:
            return grant

        grant.connect_material_payload = payload
        if self.trade_repository is not None:
            self.trade_repository.save_access_grant(grant)
            self.trade_repository.commit()
        elif self.store is not None:
            self.store.access_grants[grant.id] = grant
        self._write_grant_download_artifact(grant)
        return grant

    def _grant_payload_with_runtime_session(
        self,
        payload: dict[str, Any] | None,
        *,
        session: RuntimeSessionRecord,
    ) -> dict[str, Any]:
        merged = dict(payload or {})
        merged["runtime_session_id"] = session.id
        merged["runtime_session_status"] = session.status
        merged["runtime_bundle_status"] = session.runtime_bundle_status
        merged["runtime_service_name"] = session.runtime_service_name
        merged["gateway_service_name"] = session.gateway_service_name
        merged["network_name"] = session.network_name
        merged.update(dict(session.connect_metadata or {}))
        lease = dict(session.wireguard_lease_metadata or {})
        if lease:
            merged.setdefault("server_interface", lease.get("server_interface"))
            merged.setdefault("lease_type", lease.get("lease_type"))
            for key in (
                "server_public_key",
                "server_access_ip",
                "endpoint_host",
                "endpoint_port",
                "allowed_ips",
                "client_allowed_ips",
                "persistent_keepalive",
                "client_address",
            ):
                if lease.get(key) is not None:
                    merged[key] = lease.get(key)
        return merged

    def _sync_grant_and_order_from_runtime_session(self, session: RuntimeSessionRecord) -> None:
        grant = self.trade_repository.get_access_grant(session.access_grant_id) if self.trade_repository is not None else self.store.access_grants.get(session.access_grant_id)
        order = self.trade_repository.get_order(session.order_id) if self.trade_repository is not None else self.store.orders.get(session.order_id)
        changed = False
        if grant is not None:
            expected_payload = self._grant_payload_with_runtime_session(grant.connect_material_payload, session=session)
            if grant.connect_material_payload != expected_payload:
                grant.connect_material_payload = expected_payload
                changed = True
            if grant.runtime_session_id != session.id:
                grant.runtime_session_id = session.id
                changed = True
            if session.closed_at is not None and grant.status != "exhausted":
                grant.status = "exhausted"
                changed = True
            elif session.closed_at is None and grant.status != "redeemed":
                grant.status = "redeemed"
                changed = True
        if order is not None:
            desired_runtime_bundle_status = session.runtime_bundle_status
            if order.runtime_bundle_status != desired_runtime_bundle_status:
                order.runtime_bundle_status = desired_runtime_bundle_status
                order.updated_at = session.updated_at
                changed = True
            if session.closed_at is None and order.status != "session_active":
                order.status = "session_active"
                order.updated_at = session.updated_at
                changed = True
            if session.closed_at is not None and order.status != "completed":
                order.status = "completed"
                order.updated_at = session.updated_at
                changed = True
        if not changed:
            return
        if self.trade_repository is not None:
            if grant is not None:
                self.trade_repository.save_access_grant(grant)
                self._write_grant_download_artifact(grant)
            if order is not None:
                self.trade_repository.save_order(order)
            self.trade_repository.commit()
        else:
            if grant is not None:
                self.store.access_grants[grant.id] = grant
            if order is not None:
                self.store.orders[order.id] = order

    def _close_or_stop_runtime_session(
        self,
        buyer_user_id: str,
        runtime_session_id: str,
        *,
        allow_admin: bool,
        close_mode: str,
    ) -> RuntimeSessionRead:
        session = self._get_runtime_session_record(runtime_session_id)
        if session is None:
            raise ValueError("Runtime session not found.")
        if not allow_admin and session.buyer_user_id != buyer_user_id:
            raise ValueError("Runtime session not found.")
        if self.adapter_client is not None:
            try:
                self.adapter_client.remove_runtime_session_bundle({"session_id": session.id, "force": True})
            except AdapterClientError as exc:
                raise ValueError(f"Runtime session {close_mode} failed: {exc.detail}") from exc
        now = datetime.now(UTC)
        session.closed_at = now
        session.updated_at = now
        session.runtime_bundle_status = "removed"
        session.status = "closed"
        session.recent_error_summary = []
        self._sync_grant_and_order_from_runtime_session(session)
        self._persist_runtime_session_only(session)
        return self._runtime_session_read(session)

    @staticmethod
    def _runtime_session_status(runtime_bundle_status: str) -> str:
        lowered = runtime_bundle_status.lower()
        if lowered == "running":
            return "ready"
        if lowered in {"created", "provisioning", "allocated"}:
            return "allocating"
        if lowered == "removed":
            return "closed"
        if lowered == "failed":
            return "failed"
        return lowered or "created"

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _session_connect_metadata(connect_metadata: dict[str, Any]) -> dict[str, Any]:
        return dict(connect_metadata)
