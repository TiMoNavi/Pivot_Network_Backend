from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend_app.clients.adapter_client import AdapterClient, AdapterClientError
from backend_app.core.security import new_access_token, new_object_id
from backend_app.schemas.seller_onboarding import (
    CorrectionRead,
    CorrectionWrite,
    ContainerRuntimeProbeRead,
    ContainerRuntimeProbeWrite,
    JoinCompleteRead,
    JoinCompleteWrite,
    JoinSessionCreateRequest,
    JoinSessionRead,
    LinuxHostProbeRead,
    LinuxHostProbeWrite,
    LinuxSubstrateProbeRead,
    LinuxSubstrateProbeWrite,
    ManagerAddressOverrideRead,
    ManagerAddressOverrideWrite,
    ManagerAcceptanceRead,
    ManagerReverifyWrite,
    MinimumTcpValidationRead,
    MinimumTcpValidationWrite,
    NodeProbeSummaryRead,
    NodeResourceSummaryRead,
    SwarmJoinMaterialRead,
)
from backend_app.storage.memory_store import (
    CorrectionRecord,
    ContainerRuntimeProbeRecord,
    InMemoryStore,
    JoinCompleteRecord,
    JoinSessionRecord,
    LinuxHostProbeRecord,
    LinuxSubstrateProbeRecord,
    ManagerAddressOverrideRecord,
    ManagerAcceptanceRecord,
    MinimumTcpValidationRecord,
)


TERMINAL_SESSION_STATUSES = {"expired", "closed"}


class SellerOnboardingService:
    def __init__(
        self,
        store: InMemoryStore,
        adapter_client: AdapterClient,
        *,
        session_ttl_minutes: int = 60,
    ) -> None:
        self.store = store
        self.adapter_client = adapter_client
        self.session_ttl_minutes = session_ttl_minutes

    def create_session(self, seller_user_id: str, payload: JoinSessionCreateRequest) -> JoinSessionRead:
        now = datetime.now(UTC)
        requested_expected_wireguard_ip = self._clean_optional_string(payload.expected_wireguard_ip)
        join_material = self.adapter_client.get_join_material(
            {
                "seller_user_id": seller_user_id,
                "requested_accelerator": payload.requested_accelerator,
                "requested_compute_node_id": payload.requested_compute_node_id,
                "expected_wireguard_ip": requested_expected_wireguard_ip,
            }
        )
        expected_wireguard_ip = self._clean_optional_string(join_material.get("expected_wireguard_ip")) or requested_expected_wireguard_ip
        requested_compute_node_id = self._clean_optional_string(payload.requested_compute_node_id) or self._clean_optional_string(
            join_material.get("recommended_compute_node_id")
        )
        required_labels = self._string_dict(join_material.get("recommended_labels"))
        join_material_snapshot = dict(join_material)
        join_material_snapshot["expected_wireguard_ip"] = expected_wireguard_ip

        session = JoinSessionRecord(
            id=new_object_id("join_session"),
            seller_user_id=seller_user_id,
            status="issued",
            one_time_token=new_access_token(),
            requested_offer_tier=self._clean_optional_string(payload.requested_offer_tier),
            requested_accelerator=payload.requested_accelerator,
            requested_compute_node_id=requested_compute_node_id,
            swarm_join_material=join_material_snapshot,
            required_labels=required_labels,
            expected_wireguard_ip=expected_wireguard_ip,
            expires_at=now + timedelta(minutes=self.session_ttl_minutes),
            last_heartbeat_at=now,
            created_at=now,
            updated_at=now,
        )
        self.store.join_sessions[session.id] = session
        self.store.manager_acceptance_by_session_id[session.id] = self._pending_acceptance(
            session,
            node_ref=None,
            compute_node_id=requested_compute_node_id,
            detail="not_checked",
        )
        return self._session_read(session)

    def get_session(self, seller_user_id: str, session_id: str, *, allow_admin: bool = False) -> JoinSessionRead:
        session = self._get_owned_session(seller_user_id, session_id, allow_admin=allow_admin)
        self._expire_if_needed(session)
        return self._session_read(session)

    def submit_linux_host_probe(
        self,
        seller_user_id: str,
        session_id: str,
        payload: LinuxHostProbeWrite,
        *,
        allow_admin: bool = False,
    ) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        self.store.linux_host_probes_by_session_id[session.id] = LinuxHostProbeRecord(
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase=self._clean_optional_string(payload.reported_phase),
            host_name=self._clean_optional_string(payload.host_name),
            os_name=self._clean_optional_string(payload.os_name),
            distribution_name=self._clean_optional_string(payload.distribution_name),
            kernel_release=self._clean_optional_string(payload.kernel_release),
            virtualization_available=payload.virtualization_available,
            sudo_available=payload.sudo_available,
            observed_ips=list(payload.observed_ips),
            notes=list(payload.notes),
            raw_payload=dict(payload.raw_payload),
            recorded_at=now,
        )
        self._clear_verification_state(session, detail="awaiting_join_complete")
        self._touch_session(session, status="probing", when=now)
        return self._session_read(session)

    def submit_linux_substrate_probe(
        self,
        seller_user_id: str,
        session_id: str,
        payload: LinuxSubstrateProbeWrite,
        *,
        allow_admin: bool = False,
    ) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        probe = LinuxSubstrateProbeRecord(
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase=self._clean_optional_string(payload.reported_phase),
            distribution_name=self._clean_optional_string(payload.distribution_name),
            kernel_release=self._clean_optional_string(payload.kernel_release),
            docker_available=payload.docker_available,
            docker_version=self._clean_optional_string(payload.docker_version),
            wireguard_available=payload.wireguard_available,
            gpu_available=payload.gpu_available,
            cpu_cores=payload.cpu_cores,
            memory_gb=payload.memory_gb,
            disk_free_gb=payload.disk_free_gb,
            observed_ips=list(payload.observed_ips),
            observed_wireguard_ip=self._clean_optional_string(payload.observed_wireguard_ip),
            observed_advertise_addr=self._clean_optional_string(payload.observed_advertise_addr),
            observed_data_path_addr=self._clean_optional_string(payload.observed_data_path_addr),
            notes=list(payload.notes),
            raw_payload=dict(payload.raw_payload),
            recorded_at=now,
        )
        self.store.linux_substrate_probes_by_session_id[session.id] = probe
        self._adopt_observed_wireguard_ip(session, probe.observed_wireguard_ip)
        self._clear_verification_state(session, detail="awaiting_join_complete")
        self._touch_session(session, status="probing", when=now)
        return self._session_read(session)

    def submit_container_runtime_probe(
        self,
        seller_user_id: str,
        session_id: str,
        payload: ContainerRuntimeProbeWrite,
        *,
        allow_admin: bool = False,
    ) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        self.store.container_runtime_probes_by_session_id[session.id] = ContainerRuntimeProbeRecord(
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase=self._clean_optional_string(payload.reported_phase),
            runtime_name=self._clean_optional_string(payload.runtime_name),
            runtime_version=self._clean_optional_string(payload.runtime_version),
            engine_available=payload.engine_available,
            image_store_accessible=payload.image_store_accessible,
            network_ready=payload.network_ready,
            observed_images=list(payload.observed_images),
            notes=list(payload.notes),
            raw_payload=dict(payload.raw_payload),
            recorded_at=now,
        )
        self._touch_session(session, status="probing" if session.status == "issued" else None, when=now)
        return self._session_read(session)

    def submit_join_complete(
        self,
        seller_user_id: str,
        session_id: str,
        payload: JoinCompleteWrite,
        *,
        allow_admin: bool = False,
    ) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        compute_node_id = self._clean_optional_string(payload.compute_node_id) or session.requested_compute_node_id
        join_complete = JoinCompleteRecord(
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase=self._clean_optional_string(payload.reported_phase),
            node_ref=self._clean_optional_string(payload.node_ref),
            compute_node_id=compute_node_id,
            observed_wireguard_ip=self._clean_optional_string(payload.observed_wireguard_ip),
            observed_advertise_addr=self._clean_optional_string(payload.observed_advertise_addr),
            observed_data_path_addr=self._clean_optional_string(payload.observed_data_path_addr),
            notes=list(payload.notes),
            raw_payload=dict(payload.raw_payload),
            submitted_at=now,
        )
        self.store.join_completions_by_session_id[session.id] = join_complete
        if compute_node_id:
            session.requested_compute_node_id = compute_node_id
        self._adopt_observed_wireguard_ip(session, join_complete.observed_wireguard_ip)
        self._touch_session(session, status="joined", when=now)

        acceptance = self._evaluate_manager_acceptance(session, join_complete)
        self._set_manager_acceptance(session, acceptance, append_history=True)
        if acceptance.status == "matched":
            session.status = "verified"
        elif acceptance.status == "pending":
            session.status = "joined"
        else:
            session.status = "verify_failed"
        session.updated_at = now
        session.last_heartbeat_at = now
        return self._session_read(session)

    def submit_correction(
        self,
        seller_user_id: str,
        session_id: str,
        payload: CorrectionWrite,
        *,
        allow_admin: bool = False,
    ) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        correction = CorrectionRecord(
            id=new_object_id("correction"),
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase=self._clean_optional_string(payload.reported_phase),
            source_surface=self._clean_optional_string(payload.source_surface),
            correction_action=payload.correction_action.strip(),
            target_wireguard_ip=self._clean_optional_string(payload.target_wireguard_ip),
            observed_advertise_addr=self._clean_optional_string(payload.observed_advertise_addr),
            observed_data_path_addr=self._clean_optional_string(payload.observed_data_path_addr),
            notes=list(payload.notes),
            raw_payload=dict(payload.raw_payload),
            recorded_at=now,
        )
        self.store.corrections_by_session_id.setdefault(session.id, []).append(correction)
        self.store.minimum_tcp_validation_by_session_id.pop(session.id, None)

        last_join_complete = self.store.join_completions_by_session_id.get(session.id)
        node_ref, compute_node_id = self._acceptance_locator(session)
        detail = "awaiting_manager_reverify" if last_join_complete is not None else "correction_recorded_awaiting_join_complete"
        self._set_manager_acceptance(
            session,
            self._pending_acceptance(
                session,
                node_ref=node_ref,
                compute_node_id=compute_node_id,
                detail=detail,
            ),
            append_history=False,
        )
        self._touch_session(session, status="joined" if last_join_complete is not None else None, when=now)
        return self._session_read(session)

    def submit_manager_address_override(
        self,
        seller_user_id: str,
        session_id: str,
        payload: ManagerAddressOverrideWrite,
        *,
        allow_admin: bool = False,
    ) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        record = ManagerAddressOverrideRecord(
            id=new_object_id("manager_override"),
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase=self._clean_optional_string(payload.reported_phase),
            source_surface=self._clean_optional_string(payload.source_surface),
            override_target_addr=payload.override_target_addr.strip(),
            override_reason=payload.override_reason.strip(),
            notes=list(payload.notes),
            raw_payload=dict(payload.raw_payload),
            recorded_at=now,
        )
        self.store.manager_address_override_by_session_id[session.id] = record
        self._touch_session(session, when=now)
        return self._session_read(session)

    def reverify_manager_acceptance(
        self,
        seller_user_id: str,
        session_id: str,
        payload: ManagerReverifyWrite,
        *,
        allow_admin: bool = False,
    ) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        join_complete = self._reverify_join_complete(session, payload)
        if join_complete is None:
            self._set_manager_acceptance(
                session,
                self._pending_acceptance(
                    session,
                    node_ref=self._clean_optional_string(payload.node_ref),
                    compute_node_id=self._clean_optional_string(payload.compute_node_id) or session.requested_compute_node_id,
                    detail="join_complete_missing",
                ),
                append_history=False,
            )
            self._touch_session(session, status="joined", when=now)
            return self._session_read(session)

        acceptance = self._evaluate_manager_acceptance(session, join_complete)
        self._set_manager_acceptance(session, acceptance, append_history=True)
        if acceptance.status == "matched":
            session.status = "verified"
        elif acceptance.status == "pending":
            session.status = "joined"
        else:
            session.status = "verify_failed"
        session.updated_at = now
        session.last_heartbeat_at = now
        return self._session_read(session)

    def submit_minimum_tcp_validation(
        self,
        seller_user_id: str,
        session_id: str,
        payload: MinimumTcpValidationWrite,
        *,
        allow_admin: bool = False,
    ) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        acceptance = self._manager_acceptance(session)
        effective_target_addr, effective_target_source = self._effective_target(session, acceptance)
        manager_target = self._clean_optional_string(acceptance.observed_manager_node_addr)
        target_addr = self._clean_optional_string(payload.target_addr) or effective_target_addr

        validated_against_manager_target = False
        validated_against_effective_target = False
        detail: str | None = None
        if effective_target_addr is None:
            detail = "manager_acceptance_not_matched"
        elif target_addr != effective_target_addr:
            detail = "target_addr_not_effective_target"
        else:
            validated_against_effective_target = True
            validated_against_manager_target = (
                effective_target_source == "manager_matched"
                and manager_target is not None
                and target_addr == manager_target
            )
            if not payload.reachable:
                detail = "tcp_probe_failed"

        self.store.minimum_tcp_validation_by_session_id[session.id] = MinimumTcpValidationRecord(
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase=self._clean_optional_string(payload.reported_phase),
            target_addr=target_addr,
            target_port=payload.target_port,
            protocol=payload.protocol,
            reachable=payload.reachable,
            validated_against_manager_target=validated_against_manager_target,
            validated_against_effective_target=validated_against_effective_target,
            effective_target_addr=effective_target_addr,
            effective_target_source=effective_target_source,
            detail=detail,
            notes=list(payload.notes),
            raw_payload=dict(payload.raw_payload),
            checked_at=now,
        )
        self._touch_session(session, when=now)
        return self._session_read(session)

    def heartbeat(self, seller_user_id: str, session_id: str, *, allow_admin: bool = False) -> JoinSessionRead:
        session = self._get_active_session(seller_user_id, session_id, allow_admin=allow_admin)
        now = datetime.now(UTC)
        session.expires_at = now + timedelta(minutes=self.session_ttl_minutes)
        self._touch_session(session, when=now)
        return self._session_read(session)

    def close(self, seller_user_id: str, session_id: str, *, allow_admin: bool = False) -> JoinSessionRead:
        session = self._get_owned_session(seller_user_id, session_id, allow_admin=allow_admin)
        self._expire_if_needed(session)
        if session.status != "expired":
            self._touch_session(session, status="closed")
        return self._session_read(session)

    def _evaluate_manager_acceptance(
        self,
        session: JoinSessionRecord,
        join_complete: JoinCompleteRecord,
    ) -> ManagerAcceptanceRecord:
        expected_wireguard_ip = self._clean_optional_string(session.expected_wireguard_ip)
        node_ref = join_complete.node_ref
        compute_node_id = join_complete.compute_node_id or session.requested_compute_node_id
        if not node_ref and not compute_node_id:
            return self._pending_acceptance(
                session,
                node_ref=node_ref,
                compute_node_id=compute_node_id,
                detail="node_reference_missing",
            )

        checked_at = datetime.now(UTC)
        try:
            payload = self._inspect_for_acceptance(compute_node_id=compute_node_id, node_ref=node_ref)
        except AdapterClientError as exc:
            status = "node_not_found" if exc.status_code == 404 else "inspect_failed"
            return ManagerAcceptanceRecord(
                status=status,
                expected_wireguard_ip=expected_wireguard_ip,
                observed_manager_node_addr=None,
                matched=False,
                node_ref=node_ref,
                compute_node_id=compute_node_id,
                checked_at=checked_at,
                detail=exc.detail,
            )

        node = payload.get("node") or {}
        observed_manager_node_addr = self._clean_optional_string(node.get("node_addr"))
        resolved_node_ref = self._clean_optional_string(node.get("id")) or node_ref
        resolved_compute_node_id = compute_node_id or self._clean_optional_string(node.get("compute_node_id"))

        if self._claim_required(session):
            if not resolved_node_ref or not resolved_compute_node_id:
                return ManagerAcceptanceRecord(
                    status="claim_failed",
                    expected_wireguard_ip=expected_wireguard_ip,
                    observed_manager_node_addr=observed_manager_node_addr,
                    matched=False,
                    node_ref=resolved_node_ref,
                    compute_node_id=resolved_compute_node_id,
                    checked_at=checked_at,
                    detail="claim_locator_missing",
                )
            try:
                self.adapter_client.claim_node(
                    {
                        "node_ref": resolved_node_ref,
                        "compute_node_id": resolved_compute_node_id,
                        "seller_user_id": session.seller_user_id,
                        "accelerator": session.requested_accelerator,
                    }
                )
            except AdapterClientError as exc:
                return ManagerAcceptanceRecord(
                    status="claim_failed",
                    expected_wireguard_ip=expected_wireguard_ip,
                    observed_manager_node_addr=observed_manager_node_addr,
                    matched=False,
                    node_ref=resolved_node_ref,
                    compute_node_id=resolved_compute_node_id,
                    checked_at=checked_at,
                    detail=exc.detail,
                )
            try:
                payload = self.adapter_client.inspect_node(resolved_node_ref)
            except AdapterClientError as exc:
                status = "node_not_found" if exc.status_code == 404 else "inspect_failed"
                return ManagerAcceptanceRecord(
                    status=status,
                    expected_wireguard_ip=expected_wireguard_ip,
                    observed_manager_node_addr=None,
                    matched=False,
                    node_ref=resolved_node_ref,
                    compute_node_id=resolved_compute_node_id,
                    checked_at=checked_at,
                    detail=exc.detail,
                )
            node = payload.get("node") or {}
            observed_manager_node_addr = self._clean_optional_string(node.get("node_addr"))
            resolved_node_ref = resolved_node_ref or self._clean_optional_string(node.get("id"))
            resolved_compute_node_id = resolved_compute_node_id or self._clean_optional_string(node.get("compute_node_id"))

        if not expected_wireguard_ip:
            return ManagerAcceptanceRecord(
                status="pending",
                expected_wireguard_ip=None,
                observed_manager_node_addr=observed_manager_node_addr,
                matched=None,
                node_ref=resolved_node_ref,
                compute_node_id=resolved_compute_node_id,
                checked_at=checked_at,
                detail="expected_wireguard_ip_missing",
            )

        matched = observed_manager_node_addr == expected_wireguard_ip if observed_manager_node_addr else False
        return ManagerAcceptanceRecord(
            status="matched" if matched else "mismatch",
            expected_wireguard_ip=expected_wireguard_ip,
            observed_manager_node_addr=observed_manager_node_addr,
            matched=matched,
            node_ref=resolved_node_ref,
            compute_node_id=resolved_compute_node_id,
            checked_at=checked_at,
            detail=None if matched else "manager_node_addr_mismatch",
        )

    def _inspect_for_acceptance(
        self,
        *,
        compute_node_id: str | None,
        node_ref: str | None,
    ) -> dict[str, Any]:
        if compute_node_id:
            try:
                return self.adapter_client.inspect_node_by_compute_node_id(compute_node_id)
            except AdapterClientError as exc:
                if exc.status_code != 404 or not node_ref:
                    raise
        if node_ref:
            return self.adapter_client.inspect_node(node_ref)
        raise AdapterClientError(404, "node_reference_missing", {"detail": "node_reference_missing"})

    def _acceptance_locator(self, session: JoinSessionRecord) -> tuple[str | None, str | None]:
        join_complete = self.store.join_completions_by_session_id.get(session.id)
        if join_complete is not None:
            return join_complete.node_ref, join_complete.compute_node_id or session.requested_compute_node_id

        acceptance = self.store.manager_acceptance_by_session_id.get(session.id)
        node_ref = None if acceptance is None else acceptance.node_ref
        compute_node_id = None if acceptance is None else acceptance.compute_node_id
        return node_ref, compute_node_id or session.requested_compute_node_id

    def _reverify_join_complete(
        self,
        session: JoinSessionRecord,
        payload: ManagerReverifyWrite,
    ) -> JoinCompleteRecord | None:
        existing = self.store.join_completions_by_session_id.get(session.id)
        node_ref = self._clean_optional_string(payload.node_ref)
        compute_node_id = self._clean_optional_string(payload.compute_node_id)
        if existing is not None:
            node_ref = node_ref or existing.node_ref
            compute_node_id = compute_node_id or existing.compute_node_id or session.requested_compute_node_id
            return JoinCompleteRecord(
                join_session_id=existing.join_session_id,
                seller_user_id=existing.seller_user_id,
                reported_phase=self._clean_optional_string(payload.reported_phase) or existing.reported_phase,
                node_ref=node_ref,
                compute_node_id=compute_node_id,
                observed_wireguard_ip=existing.observed_wireguard_ip,
                observed_advertise_addr=existing.observed_advertise_addr,
                observed_data_path_addr=existing.observed_data_path_addr,
                notes=list(existing.notes) + list(payload.notes),
                raw_payload={**existing.raw_payload, **payload.raw_payload},
                submitted_at=existing.submitted_at,
            )
        if node_ref is None and compute_node_id is None:
            return None
        return JoinCompleteRecord(
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase=self._clean_optional_string(payload.reported_phase),
            node_ref=node_ref,
            compute_node_id=compute_node_id or session.requested_compute_node_id,
            observed_wireguard_ip=None,
            observed_advertise_addr=None,
            observed_data_path_addr=None,
            notes=list(payload.notes),
            raw_payload=dict(payload.raw_payload),
            submitted_at=datetime.now(UTC),
        )

    @staticmethod
    def _claim_required(session: JoinSessionRecord) -> bool:
        return bool(session.swarm_join_material.get("claim_required"))

    def _session_read(self, session: JoinSessionRecord) -> JoinSessionRead:
        return JoinSessionRead(
            session_id=session.id,
            seller_user_id=session.seller_user_id,
            status=session.status,
            one_time_token=session.one_time_token,
            requested_offer_tier=session.requested_offer_tier,
            requested_accelerator=session.requested_accelerator,
            requested_compute_node_id=session.requested_compute_node_id,
            swarm_join_material=SwarmJoinMaterialRead(**session.swarm_join_material),
            required_labels=dict(session.required_labels),
            expected_wireguard_ip=session.expected_wireguard_ip,
            probe_summary=self._probe_summary_read(session),
            container_runtime_probe=self._container_runtime_probe_read(
                self.store.container_runtime_probes_by_session_id.get(session.id)
            ),
            last_join_complete=self._join_complete_read(self.store.join_completions_by_session_id.get(session.id)),
            correction_history=self._correction_history_read(session),
            manager_address_override=self._manager_address_override_read(
                self.store.manager_address_override_by_session_id.get(session.id)
            ),
            manager_acceptance=self._manager_acceptance_read(self._manager_acceptance(session)),
            manager_acceptance_history=self._manager_acceptance_history_read(session),
            effective_target_addr=self._effective_target(session, self._manager_acceptance(session))[0],
            effective_target_source=self._effective_target(session, self._manager_acceptance(session))[1],
            minimum_tcp_validation=self._minimum_tcp_validation_read(
                self.store.minimum_tcp_validation_by_session_id.get(session.id)
            ),
            expires_at=session.expires_at,
            last_heartbeat_at=session.last_heartbeat_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def _probe_summary_read(self, session: JoinSessionRecord) -> NodeProbeSummaryRead:
        host_probe = self.store.linux_host_probes_by_session_id.get(session.id)
        substrate_probe = self.store.linux_substrate_probes_by_session_id.get(session.id)
        updated_at = max(
            [item.recorded_at for item in [host_probe, substrate_probe] if item is not None] or [session.updated_at]
        )
        return NodeProbeSummaryRead(
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            linux_host_probe=self._linux_host_probe_read(host_probe),
            linux_substrate_probe=self._linux_substrate_probe_read(substrate_probe),
            resource_summary=NodeResourceSummaryRead(
                docker_available=None if substrate_probe is None else substrate_probe.docker_available,
                wireguard_available=None if substrate_probe is None else substrate_probe.wireguard_available,
                gpu_available=None if substrate_probe is None else substrate_probe.gpu_available,
                cpu_cores=None if substrate_probe is None else substrate_probe.cpu_cores,
                memory_gb=None if substrate_probe is None else substrate_probe.memory_gb,
                disk_free_gb=None if substrate_probe is None else substrate_probe.disk_free_gb,
            ),
            validation_warnings=self._validation_warnings(host_probe, substrate_probe),
            updated_at=updated_at,
        )

    def _validation_warnings(
        self,
        host_probe: LinuxHostProbeRecord | None,
        substrate_probe: LinuxSubstrateProbeRecord | None,
    ) -> list[str]:
        warnings: list[str] = []
        if host_probe is None:
            warnings.append("linux_host_probe_missing")
        elif host_probe.virtualization_available is False:
            warnings.append("linux_host_virtualization_unavailable")

        if substrate_probe is None:
            warnings.append("linux_substrate_probe_missing")
            return warnings

        if substrate_probe.docker_available is False:
            warnings.append("linux_substrate_docker_unavailable")
        if substrate_probe.wireguard_available is False:
            warnings.append("linux_substrate_wireguard_unavailable")
        if not substrate_probe.observed_wireguard_ip:
            warnings.append("linux_substrate_wireguard_ip_missing")
        return warnings

    def _linux_host_probe_read(self, record: LinuxHostProbeRecord | None) -> LinuxHostProbeRead | None:
        if record is None:
            return None
        return LinuxHostProbeRead(
            join_session_id=record.join_session_id,
            seller_user_id=record.seller_user_id,
            reported_phase=record.reported_phase,
            host_name=record.host_name,
            os_name=record.os_name,
            distribution_name=record.distribution_name,
            kernel_release=record.kernel_release,
            virtualization_available=record.virtualization_available,
            sudo_available=record.sudo_available,
            observed_ips=list(record.observed_ips),
            notes=list(record.notes),
            raw_payload=dict(record.raw_payload),
            recorded_at=record.recorded_at,
        )

    def _linux_substrate_probe_read(self, record: LinuxSubstrateProbeRecord | None) -> LinuxSubstrateProbeRead | None:
        if record is None:
            return None
        return LinuxSubstrateProbeRead(
            join_session_id=record.join_session_id,
            seller_user_id=record.seller_user_id,
            reported_phase=record.reported_phase,
            distribution_name=record.distribution_name,
            kernel_release=record.kernel_release,
            docker_available=record.docker_available,
            docker_version=record.docker_version,
            wireguard_available=record.wireguard_available,
            gpu_available=record.gpu_available,
            cpu_cores=record.cpu_cores,
            memory_gb=record.memory_gb,
            disk_free_gb=record.disk_free_gb,
            observed_ips=list(record.observed_ips),
            observed_wireguard_ip=record.observed_wireguard_ip,
            observed_advertise_addr=record.observed_advertise_addr,
            observed_data_path_addr=record.observed_data_path_addr,
            notes=list(record.notes),
            raw_payload=dict(record.raw_payload),
            recorded_at=record.recorded_at,
        )

    def _container_runtime_probe_read(self, record: ContainerRuntimeProbeRecord | None) -> ContainerRuntimeProbeRead | None:
        if record is None:
            return None
        return ContainerRuntimeProbeRead(
            join_session_id=record.join_session_id,
            seller_user_id=record.seller_user_id,
            reported_phase=record.reported_phase,
            runtime_name=record.runtime_name,
            runtime_version=record.runtime_version,
            engine_available=record.engine_available,
            image_store_accessible=record.image_store_accessible,
            network_ready=record.network_ready,
            observed_images=list(record.observed_images),
            notes=list(record.notes),
            raw_payload=dict(record.raw_payload),
            recorded_at=record.recorded_at,
        )

    def _join_complete_read(self, record: JoinCompleteRecord | None) -> JoinCompleteRead | None:
        if record is None:
            return None
        return JoinCompleteRead(
            join_session_id=record.join_session_id,
            seller_user_id=record.seller_user_id,
            reported_phase=record.reported_phase,
            node_ref=record.node_ref,
            compute_node_id=record.compute_node_id,
            observed_wireguard_ip=record.observed_wireguard_ip,
            observed_advertise_addr=record.observed_advertise_addr,
            observed_data_path_addr=record.observed_data_path_addr,
            notes=list(record.notes),
            raw_payload=dict(record.raw_payload),
            submitted_at=record.submitted_at,
        )

    @staticmethod
    def _correction_read(record: CorrectionRecord) -> CorrectionRead:
        return CorrectionRead(
            correction_id=record.id,
            join_session_id=record.join_session_id,
            seller_user_id=record.seller_user_id,
            reported_phase=record.reported_phase,
            source_surface=record.source_surface,
            correction_action=record.correction_action,
            target_wireguard_ip=record.target_wireguard_ip,
            observed_advertise_addr=record.observed_advertise_addr,
            observed_data_path_addr=record.observed_data_path_addr,
            notes=list(record.notes),
            raw_payload=dict(record.raw_payload),
            recorded_at=record.recorded_at,
        )

    def _correction_history_read(self, session: JoinSessionRecord) -> list[CorrectionRead]:
        return [
            self._correction_read(record)
            for record in self.store.corrections_by_session_id.get(session.id, [])
        ]

    @staticmethod
    def _manager_address_override_read(record: ManagerAddressOverrideRecord | None) -> ManagerAddressOverrideRead | None:
        if record is None:
            return None
        return ManagerAddressOverrideRead(
            override_id=record.id,
            join_session_id=record.join_session_id,
            seller_user_id=record.seller_user_id,
            reported_phase=record.reported_phase,
            source_surface=record.source_surface,
            override_target_addr=record.override_target_addr,
            override_reason=record.override_reason,
            notes=list(record.notes),
            raw_payload=dict(record.raw_payload),
            recorded_at=record.recorded_at,
        )

    @staticmethod
    def _manager_acceptance_read(record: ManagerAcceptanceRecord) -> ManagerAcceptanceRead:
        return ManagerAcceptanceRead(
            status=record.status,
            expected_wireguard_ip=record.expected_wireguard_ip,
            observed_manager_node_addr=record.observed_manager_node_addr,
            matched=record.matched,
            node_ref=record.node_ref,
            compute_node_id=record.compute_node_id,
            checked_at=record.checked_at,
            detail=record.detail,
        )

    def _manager_acceptance_history_read(self, session: JoinSessionRecord) -> list[ManagerAcceptanceRead]:
        return [
            self._manager_acceptance_read(record)
            for record in self.store.manager_acceptance_history_by_session_id.get(session.id, [])
        ]

    @staticmethod
    def _minimum_tcp_validation_read(record: MinimumTcpValidationRecord | None) -> MinimumTcpValidationRead | None:
        if record is None:
            return None
        return MinimumTcpValidationRead(
            join_session_id=record.join_session_id,
            seller_user_id=record.seller_user_id,
            reported_phase=record.reported_phase,
            target_addr=record.target_addr,
            target_port=record.target_port,
            protocol=record.protocol,
            reachable=record.reachable,
            validated_against_manager_target=record.validated_against_manager_target,
            validated_against_effective_target=record.validated_against_effective_target,
            effective_target_addr=record.effective_target_addr,
            effective_target_source=record.effective_target_source,
            detail=record.detail,
            notes=list(record.notes),
            raw_payload=dict(record.raw_payload),
            checked_at=record.checked_at,
        )

    def _effective_target(
        self,
        session: JoinSessionRecord,
        acceptance: ManagerAcceptanceRecord,
    ) -> tuple[str | None, str | None]:
        override = self.store.manager_address_override_by_session_id.get(session.id)
        if override is not None:
            return override.override_target_addr, "operator_override"
        manager_target = self._clean_optional_string(acceptance.observed_manager_node_addr)
        if acceptance.status == "matched" and manager_target is not None:
            return manager_target, "manager_matched"
        return None, None

    def _manager_acceptance(self, session: JoinSessionRecord) -> ManagerAcceptanceRecord:
        acceptance = self.store.manager_acceptance_by_session_id.get(session.id)
        if acceptance is not None:
            return acceptance
        acceptance = self._pending_acceptance(
            session,
            node_ref=None,
            compute_node_id=session.requested_compute_node_id,
            detail="not_checked",
        )
        self.store.manager_acceptance_by_session_id[session.id] = acceptance
        return acceptance

    def _set_manager_acceptance(
        self,
        session: JoinSessionRecord,
        acceptance: ManagerAcceptanceRecord,
        *,
        append_history: bool,
    ) -> None:
        self.store.manager_acceptance_by_session_id[session.id] = acceptance
        if append_history:
            self.store.manager_acceptance_history_by_session_id.setdefault(session.id, []).append(acceptance)

    def _pending_acceptance(
        self,
        session: JoinSessionRecord,
        *,
        node_ref: str | None,
        compute_node_id: str | None,
        detail: str,
    ) -> ManagerAcceptanceRecord:
        return ManagerAcceptanceRecord(
            status="pending",
            expected_wireguard_ip=session.expected_wireguard_ip,
            observed_manager_node_addr=None,
            matched=None,
            node_ref=node_ref,
            compute_node_id=compute_node_id,
            checked_at=None,
            detail=detail,
        )

    def _clear_verification_state(self, session: JoinSessionRecord, *, detail: str) -> None:
        self.store.join_completions_by_session_id.pop(session.id, None)
        self.store.minimum_tcp_validation_by_session_id.pop(session.id, None)
        self._set_manager_acceptance(
            session,
            self._pending_acceptance(
                session,
                node_ref=None,
                compute_node_id=session.requested_compute_node_id,
                detail=detail,
            ),
            append_history=False,
        )

    def _adopt_observed_wireguard_ip(self, session: JoinSessionRecord, observed_wireguard_ip: str | None) -> None:
        candidate = self._clean_optional_string(observed_wireguard_ip)
        if session.expected_wireguard_ip is not None or candidate is None:
            return
        session.expected_wireguard_ip = candidate
        session.swarm_join_material["expected_wireguard_ip"] = candidate

    def _touch_session(
        self,
        session: JoinSessionRecord,
        *,
        status: str | None = None,
        when: datetime | None = None,
    ) -> None:
        moment = when or datetime.now(UTC)
        if status is not None:
            session.status = status
        session.last_heartbeat_at = moment
        session.updated_at = moment

    def _get_active_session(self, seller_user_id: str, session_id: str, *, allow_admin: bool) -> JoinSessionRecord:
        session = self._get_owned_session(seller_user_id, session_id, allow_admin=allow_admin)
        self._expire_if_needed(session)
        if session.status in TERMINAL_SESSION_STATUSES:
            raise ValueError("Onboarding session is not active.")
        return session

    def _get_owned_session(self, seller_user_id: str, session_id: str, *, allow_admin: bool) -> JoinSessionRecord:
        session = self.store.join_sessions.get(session_id)
        if session is None:
            raise ValueError("Onboarding session not found.")
        if not allow_admin and session.seller_user_id != seller_user_id:
            raise ValueError("Onboarding session not found.")
        return session

    def _expire_if_needed(self, session: JoinSessionRecord) -> None:
        if session.status in TERMINAL_SESSION_STATUSES:
            return
        if session.expires_at <= datetime.now(UTC):
            self._touch_session(session, status="expired")

    @staticmethod
    def _clean_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _string_dict(payload: Any) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items()}
