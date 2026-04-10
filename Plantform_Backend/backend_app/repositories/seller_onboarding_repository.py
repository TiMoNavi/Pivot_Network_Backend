from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.seller_onboarding import (
    SellerOnboardingAuthoritativeEffectiveTargetModel,
    SellerOnboardingContainerRuntimeProbeModel,
    SellerOnboardingCorrectionModel,
    SellerOnboardingJoinCompleteModel,
    SellerOnboardingLinuxHostProbeModel,
    SellerOnboardingLinuxSubstrateProbeModel,
    SellerOnboardingManagerAcceptanceHistoryModel,
    SellerOnboardingManagerAcceptanceModel,
    SellerOnboardingManagerAddressOverrideModel,
    SellerOnboardingMinimumTcpValidationModel,
    SellerOnboardingSessionModel,
)
from backend_app.storage.memory_store import (
    AuthoritativeEffectiveTargetRecord,
    CorrectionRecord,
    ContainerRuntimeProbeRecord,
    JoinCompleteRecord,
    JoinSessionRecord,
    LinuxHostProbeRecord,
    LinuxSubstrateProbeRecord,
    ManagerAddressOverrideRecord,
    ManagerAcceptanceRecord,
    MinimumTcpValidationRecord,
)


class SellerOnboardingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def save_session(self, record: JoinSessionRecord) -> JoinSessionRecord:
        model = self.session.get(SellerOnboardingSessionModel, record.id)
        if model is None:
            model = SellerOnboardingSessionModel(id=record.id)
            self.session.add(model)
        model.seller_user_id = record.seller_user_id
        model.status = record.status
        model.one_time_token = record.one_time_token
        model.requested_offer_tier = record.requested_offer_tier
        model.requested_accelerator = record.requested_accelerator
        model.requested_compute_node_id = record.requested_compute_node_id
        model.swarm_join_material = dict(record.swarm_join_material)
        model.required_labels = dict(record.required_labels)
        model.expected_wireguard_ip = record.expected_wireguard_ip
        model.expires_at = self._ensure_utc_datetime(record.expires_at)
        model.last_heartbeat_at = self._ensure_utc_datetime(record.last_heartbeat_at)
        model.created_at = self._ensure_utc_datetime(record.created_at)
        model.updated_at = self._ensure_utc_datetime(record.updated_at)
        self.session.flush()
        return self._session_record(model)

    def get_session(self, session_id: str) -> JoinSessionRecord | None:
        model = self.session.get(SellerOnboardingSessionModel, session_id)
        if model is None:
            return None
        return self._session_record(model)

    def list_sessions_for_seller(self, seller_user_id: str) -> list[JoinSessionRecord]:
        statement = (
            select(SellerOnboardingSessionModel)
            .where(SellerOnboardingSessionModel.seller_user_id == seller_user_id)
            .order_by(SellerOnboardingSessionModel.updated_at.desc())
        )
        return [self._session_record(model) for model in self.session.scalars(statement)]

    def latest_session_for_seller(self, seller_user_id: str) -> JoinSessionRecord | None:
        statement = (
            select(SellerOnboardingSessionModel)
            .where(SellerOnboardingSessionModel.seller_user_id == seller_user_id)
            .order_by(SellerOnboardingSessionModel.updated_at.desc())
            .limit(1)
        )
        model = self.session.scalar(statement)
        if model is None:
            return None
        return self._session_record(model)

    def list_sessions_for_compute_node_id(
        self,
        compute_node_id: str,
        *,
        seller_user_id: str | None = None,
    ) -> list[JoinSessionRecord]:
        statement = select(SellerOnboardingSessionModel).where(
            SellerOnboardingSessionModel.requested_compute_node_id == compute_node_id
        )
        if seller_user_id is not None:
            statement = statement.where(SellerOnboardingSessionModel.seller_user_id == seller_user_id)
        statement = statement.order_by(SellerOnboardingSessionModel.updated_at.desc())
        return [self._session_record(model) for model in self.session.scalars(statement)]

    def save_linux_host_probe(self, record: LinuxHostProbeRecord) -> None:
        model = self.session.get(SellerOnboardingLinuxHostProbeModel, record.join_session_id)
        if model is None:
            model = SellerOnboardingLinuxHostProbeModel(join_session_id=record.join_session_id)
            self.session.add(model)
        model.seller_user_id = record.seller_user_id
        model.reported_phase = record.reported_phase
        model.host_name = record.host_name
        model.os_name = record.os_name
        model.distribution_name = record.distribution_name
        model.kernel_release = record.kernel_release
        model.virtualization_available = record.virtualization_available
        model.sudo_available = record.sudo_available
        model.observed_ips = list(record.observed_ips)
        model.notes = list(record.notes)
        model.raw_payload = dict(record.raw_payload)
        model.recorded_at = self._ensure_utc_datetime(record.recorded_at)
        self.session.flush()

    def get_linux_host_probe(self, session_id: str) -> LinuxHostProbeRecord | None:
        model = self.session.get(SellerOnboardingLinuxHostProbeModel, session_id)
        if model is None:
            return None
        return LinuxHostProbeRecord(
            join_session_id=model.join_session_id,
            seller_user_id=model.seller_user_id,
            reported_phase=model.reported_phase,
            host_name=model.host_name,
            os_name=model.os_name,
            distribution_name=model.distribution_name,
            kernel_release=model.kernel_release,
            virtualization_available=model.virtualization_available,
            sudo_available=model.sudo_available,
            observed_ips=list(model.observed_ips or []),
            notes=list(model.notes or []),
            raw_payload=dict(model.raw_payload or {}),
            recorded_at=self._ensure_utc_datetime(model.recorded_at),
        )

    def save_linux_substrate_probe(self, record: LinuxSubstrateProbeRecord) -> None:
        model = self.session.get(SellerOnboardingLinuxSubstrateProbeModel, record.join_session_id)
        if model is None:
            model = SellerOnboardingLinuxSubstrateProbeModel(join_session_id=record.join_session_id)
            self.session.add(model)
        model.seller_user_id = record.seller_user_id
        model.reported_phase = record.reported_phase
        model.distribution_name = record.distribution_name
        model.kernel_release = record.kernel_release
        model.docker_available = record.docker_available
        model.docker_version = record.docker_version
        model.wireguard_available = record.wireguard_available
        model.gpu_available = record.gpu_available
        model.cpu_cores = record.cpu_cores
        model.memory_gb = record.memory_gb
        model.disk_free_gb = record.disk_free_gb
        model.observed_ips = list(record.observed_ips)
        model.observed_wireguard_ip = record.observed_wireguard_ip
        model.observed_advertise_addr = record.observed_advertise_addr
        model.observed_data_path_addr = record.observed_data_path_addr
        model.notes = list(record.notes)
        model.raw_payload = dict(record.raw_payload)
        model.recorded_at = self._ensure_utc_datetime(record.recorded_at)
        self.session.flush()

    def get_linux_substrate_probe(self, session_id: str) -> LinuxSubstrateProbeRecord | None:
        model = self.session.get(SellerOnboardingLinuxSubstrateProbeModel, session_id)
        if model is None:
            return None
        return LinuxSubstrateProbeRecord(
            join_session_id=model.join_session_id,
            seller_user_id=model.seller_user_id,
            reported_phase=model.reported_phase,
            distribution_name=model.distribution_name,
            kernel_release=model.kernel_release,
            docker_available=model.docker_available,
            docker_version=model.docker_version,
            wireguard_available=model.wireguard_available,
            gpu_available=model.gpu_available,
            cpu_cores=model.cpu_cores,
            memory_gb=model.memory_gb,
            disk_free_gb=model.disk_free_gb,
            observed_ips=list(model.observed_ips or []),
            observed_wireguard_ip=model.observed_wireguard_ip,
            observed_advertise_addr=model.observed_advertise_addr,
            observed_data_path_addr=model.observed_data_path_addr,
            notes=list(model.notes or []),
            raw_payload=dict(model.raw_payload or {}),
            recorded_at=self._ensure_utc_datetime(model.recorded_at),
        )

    def save_container_runtime_probe(self, record: ContainerRuntimeProbeRecord) -> None:
        model = self.session.get(SellerOnboardingContainerRuntimeProbeModel, record.join_session_id)
        if model is None:
            model = SellerOnboardingContainerRuntimeProbeModel(join_session_id=record.join_session_id)
            self.session.add(model)
        model.seller_user_id = record.seller_user_id
        model.reported_phase = record.reported_phase
        model.runtime_name = record.runtime_name
        model.runtime_version = record.runtime_version
        model.engine_available = record.engine_available
        model.image_store_accessible = record.image_store_accessible
        model.network_ready = record.network_ready
        model.observed_images = list(record.observed_images)
        model.notes = list(record.notes)
        model.raw_payload = dict(record.raw_payload)
        model.recorded_at = self._ensure_utc_datetime(record.recorded_at)
        self.session.flush()

    def get_container_runtime_probe(self, session_id: str) -> ContainerRuntimeProbeRecord | None:
        model = self.session.get(SellerOnboardingContainerRuntimeProbeModel, session_id)
        if model is None:
            return None
        return ContainerRuntimeProbeRecord(
            join_session_id=model.join_session_id,
            seller_user_id=model.seller_user_id,
            reported_phase=model.reported_phase,
            runtime_name=model.runtime_name,
            runtime_version=model.runtime_version,
            engine_available=model.engine_available,
            image_store_accessible=model.image_store_accessible,
            network_ready=model.network_ready,
            observed_images=list(model.observed_images or []),
            notes=list(model.notes or []),
            raw_payload=dict(model.raw_payload or {}),
            recorded_at=self._ensure_utc_datetime(model.recorded_at),
        )

    def save_join_complete(self, record: JoinCompleteRecord) -> None:
        model = self.session.get(SellerOnboardingJoinCompleteModel, record.join_session_id)
        if model is None:
            model = SellerOnboardingJoinCompleteModel(join_session_id=record.join_session_id)
            self.session.add(model)
        model.seller_user_id = record.seller_user_id
        model.reported_phase = record.reported_phase
        model.node_ref = record.node_ref
        model.compute_node_id = record.compute_node_id
        model.observed_wireguard_ip = record.observed_wireguard_ip
        model.observed_advertise_addr = record.observed_advertise_addr
        model.observed_data_path_addr = record.observed_data_path_addr
        model.notes = list(record.notes)
        model.raw_payload = dict(record.raw_payload)
        model.submitted_at = self._ensure_utc_datetime(record.submitted_at)
        self.session.flush()

    def get_join_complete(self, session_id: str) -> JoinCompleteRecord | None:
        model = self.session.get(SellerOnboardingJoinCompleteModel, session_id)
        if model is None:
            return None
        return JoinCompleteRecord(
            join_session_id=model.join_session_id,
            seller_user_id=model.seller_user_id,
            reported_phase=model.reported_phase,
            node_ref=model.node_ref,
            compute_node_id=model.compute_node_id,
            observed_wireguard_ip=model.observed_wireguard_ip,
            observed_advertise_addr=model.observed_advertise_addr,
            observed_data_path_addr=model.observed_data_path_addr,
            notes=list(model.notes or []),
            raw_payload=dict(model.raw_payload or {}),
            submitted_at=self._ensure_utc_datetime(model.submitted_at),
        )

    def clear_join_complete(self, session_id: str) -> None:
        model = self.session.get(SellerOnboardingJoinCompleteModel, session_id)
        if model is not None:
            self.session.delete(model)
            self.session.flush()

    def append_correction(self, record: CorrectionRecord) -> None:
        model = self.session.get(SellerOnboardingCorrectionModel, record.id)
        if model is None:
            model = SellerOnboardingCorrectionModel(id=record.id)
            self.session.add(model)
        model.join_session_id = record.join_session_id
        model.seller_user_id = record.seller_user_id
        model.reported_phase = record.reported_phase
        model.source_surface = record.source_surface
        model.correction_action = record.correction_action
        model.target_wireguard_ip = record.target_wireguard_ip
        model.observed_advertise_addr = record.observed_advertise_addr
        model.observed_data_path_addr = record.observed_data_path_addr
        model.notes = list(record.notes)
        model.raw_payload = dict(record.raw_payload)
        model.recorded_at = self._ensure_utc_datetime(record.recorded_at)
        self.session.flush()

    def list_corrections(self, session_id: str) -> list[CorrectionRecord]:
        statement = (
            select(SellerOnboardingCorrectionModel)
            .where(SellerOnboardingCorrectionModel.join_session_id == session_id)
            .order_by(SellerOnboardingCorrectionModel.recorded_at.asc(), SellerOnboardingCorrectionModel.id.asc())
        )
        return [
            CorrectionRecord(
                id=model.id,
                join_session_id=model.join_session_id,
                seller_user_id=model.seller_user_id,
                reported_phase=model.reported_phase,
                source_surface=model.source_surface,
                correction_action=model.correction_action,
                target_wireguard_ip=model.target_wireguard_ip,
                observed_advertise_addr=model.observed_advertise_addr,
                observed_data_path_addr=model.observed_data_path_addr,
                notes=list(model.notes or []),
                raw_payload=dict(model.raw_payload or {}),
                recorded_at=self._ensure_utc_datetime(model.recorded_at),
            )
            for model in self.session.scalars(statement)
        ]

    def save_manager_address_override(self, record: ManagerAddressOverrideRecord) -> None:
        statement = select(SellerOnboardingManagerAddressOverrideModel).where(
            SellerOnboardingManagerAddressOverrideModel.join_session_id == record.join_session_id
        )
        model = self.session.scalar(statement)
        if model is None:
            model = SellerOnboardingManagerAddressOverrideModel(id=record.id, join_session_id=record.join_session_id)
            self.session.add(model)
        model.id = record.id
        model.seller_user_id = record.seller_user_id
        model.reported_phase = record.reported_phase
        model.source_surface = record.source_surface
        model.override_target_addr = record.override_target_addr
        model.override_reason = record.override_reason
        model.notes = list(record.notes)
        model.raw_payload = dict(record.raw_payload)
        model.recorded_at = self._ensure_utc_datetime(record.recorded_at)
        self.session.flush()

    def get_manager_address_override(self, session_id: str) -> ManagerAddressOverrideRecord | None:
        statement = select(SellerOnboardingManagerAddressOverrideModel).where(
            SellerOnboardingManagerAddressOverrideModel.join_session_id == session_id
        )
        model = self.session.scalar(statement)
        if model is None:
            return None
        return ManagerAddressOverrideRecord(
            id=model.id,
            join_session_id=model.join_session_id,
            seller_user_id=model.seller_user_id,
            reported_phase=model.reported_phase,
            source_surface=model.source_surface,
            override_target_addr=model.override_target_addr,
            override_reason=model.override_reason,
            notes=list(model.notes or []),
            raw_payload=dict(model.raw_payload or {}),
            recorded_at=self._ensure_utc_datetime(model.recorded_at),
        )

    def save_authoritative_effective_target(self, record: AuthoritativeEffectiveTargetRecord) -> None:
        statement = select(SellerOnboardingAuthoritativeEffectiveTargetModel).where(
            SellerOnboardingAuthoritativeEffectiveTargetModel.join_session_id == record.join_session_id
        )
        model = self.session.scalar(statement)
        if model is None:
            model = SellerOnboardingAuthoritativeEffectiveTargetModel(id=record.id, join_session_id=record.join_session_id)
            self.session.add(model)
        model.id = record.id
        model.seller_user_id = record.seller_user_id
        model.reported_phase = record.reported_phase
        model.source_surface = record.source_surface
        model.effective_target_addr = record.effective_target_addr
        model.effective_target_reason = record.effective_target_reason
        model.notes = list(record.notes)
        model.raw_payload = dict(record.raw_payload)
        model.recorded_at = self._ensure_utc_datetime(record.recorded_at)
        self.session.flush()

    def get_authoritative_effective_target(self, session_id: str) -> AuthoritativeEffectiveTargetRecord | None:
        statement = select(SellerOnboardingAuthoritativeEffectiveTargetModel).where(
            SellerOnboardingAuthoritativeEffectiveTargetModel.join_session_id == session_id
        )
        model = self.session.scalar(statement)
        if model is None:
            return None
        return AuthoritativeEffectiveTargetRecord(
            id=model.id,
            join_session_id=model.join_session_id,
            seller_user_id=model.seller_user_id,
            reported_phase=model.reported_phase,
            source_surface=model.source_surface,
            effective_target_addr=model.effective_target_addr,
            effective_target_reason=model.effective_target_reason,
            notes=list(model.notes or []),
            raw_payload=dict(model.raw_payload or {}),
            recorded_at=self._ensure_utc_datetime(model.recorded_at),
        )

    def clear_authoritative_effective_target(self, session_id: str) -> None:
        statement = select(SellerOnboardingAuthoritativeEffectiveTargetModel).where(
            SellerOnboardingAuthoritativeEffectiveTargetModel.join_session_id == session_id
        )
        model = self.session.scalar(statement)
        if model is not None:
            self.session.delete(model)
            self.session.flush()

    def set_manager_acceptance(self, session_id: str, record: ManagerAcceptanceRecord, *, append_history: bool) -> None:
        model = self.session.get(SellerOnboardingManagerAcceptanceModel, session_id)
        if model is None:
            model = SellerOnboardingManagerAcceptanceModel(join_session_id=session_id)
            self.session.add(model)
        model.status = record.status
        model.expected_wireguard_ip = record.expected_wireguard_ip
        model.observed_manager_node_addr = record.observed_manager_node_addr
        model.matched = record.matched
        model.node_ref = record.node_ref
        model.compute_node_id = record.compute_node_id
        model.checked_at = self._ensure_utc_datetime(record.checked_at)
        model.detail = record.detail
        if append_history:
            self.session.add(
                SellerOnboardingManagerAcceptanceHistoryModel(
                    join_session_id=session_id,
                    status=record.status,
                    expected_wireguard_ip=record.expected_wireguard_ip,
                    observed_manager_node_addr=record.observed_manager_node_addr,
                    matched=record.matched,
                    node_ref=record.node_ref,
                    compute_node_id=record.compute_node_id,
                    checked_at=self._ensure_utc_datetime(record.checked_at),
                    detail=record.detail,
                )
            )
        self.session.flush()

    def get_manager_acceptance(self, session_id: str) -> ManagerAcceptanceRecord | None:
        model = self.session.get(SellerOnboardingManagerAcceptanceModel, session_id)
        if model is None:
            return None
        return ManagerAcceptanceRecord(
            status=model.status,
            expected_wireguard_ip=model.expected_wireguard_ip,
            observed_manager_node_addr=model.observed_manager_node_addr,
            matched=model.matched,
            node_ref=model.node_ref,
            compute_node_id=model.compute_node_id,
            checked_at=self._ensure_utc_datetime(model.checked_at),
            detail=model.detail,
        )

    def list_manager_acceptance_history(self, session_id: str) -> list[ManagerAcceptanceRecord]:
        statement = (
            select(SellerOnboardingManagerAcceptanceHistoryModel)
            .where(SellerOnboardingManagerAcceptanceHistoryModel.join_session_id == session_id)
            .order_by(
                SellerOnboardingManagerAcceptanceHistoryModel.id.asc(),
            )
        )
        return [
            ManagerAcceptanceRecord(
                status=model.status,
                expected_wireguard_ip=model.expected_wireguard_ip,
                observed_manager_node_addr=model.observed_manager_node_addr,
                matched=model.matched,
                node_ref=model.node_ref,
                compute_node_id=model.compute_node_id,
                checked_at=self._ensure_utc_datetime(model.checked_at),
                detail=model.detail,
            )
            for model in self.session.scalars(statement)
        ]

    def save_minimum_tcp_validation(self, record: MinimumTcpValidationRecord) -> None:
        model = self.session.get(SellerOnboardingMinimumTcpValidationModel, record.join_session_id)
        if model is None:
            model = SellerOnboardingMinimumTcpValidationModel(join_session_id=record.join_session_id)
            self.session.add(model)
        model.seller_user_id = record.seller_user_id
        model.reported_phase = record.reported_phase
        model.target_addr = record.target_addr
        model.target_port = record.target_port
        model.protocol = record.protocol
        model.reachable = record.reachable
        model.validated_against_manager_target = record.validated_against_manager_target
        model.validated_against_effective_target = record.validated_against_effective_target
        model.effective_target_addr = record.effective_target_addr
        model.effective_target_source = record.effective_target_source
        model.truth_authority = record.truth_authority
        model.detail = record.detail
        model.notes = list(record.notes)
        model.raw_payload = dict(record.raw_payload)
        model.checked_at = self._ensure_utc_datetime(record.checked_at)
        self.session.flush()

    def get_minimum_tcp_validation(self, session_id: str) -> MinimumTcpValidationRecord | None:
        model = self.session.get(SellerOnboardingMinimumTcpValidationModel, session_id)
        if model is None:
            return None
        return MinimumTcpValidationRecord(
            join_session_id=model.join_session_id,
            seller_user_id=model.seller_user_id,
            reported_phase=model.reported_phase,
            target_addr=model.target_addr,
            target_port=model.target_port,
            protocol=model.protocol,
            reachable=model.reachable,
            validated_against_manager_target=model.validated_against_manager_target,
            validated_against_effective_target=model.validated_against_effective_target,
            effective_target_addr=model.effective_target_addr,
            effective_target_source=model.effective_target_source,
            truth_authority=model.truth_authority,
            detail=model.detail,
            notes=list(model.notes or []),
            raw_payload=dict(model.raw_payload or {}),
            checked_at=self._ensure_utc_datetime(model.checked_at),
        )

    def clear_minimum_tcp_validation(self, session_id: str) -> None:
        model = self.session.get(SellerOnboardingMinimumTcpValidationModel, session_id)
        if model is not None:
            self.session.delete(model)
            self.session.flush()

    @staticmethod
    def _session_record(model: SellerOnboardingSessionModel) -> JoinSessionRecord:
        return JoinSessionRecord(
            id=model.id,
            seller_user_id=model.seller_user_id,
            status=model.status,
            one_time_token=model.one_time_token,
            requested_offer_tier=model.requested_offer_tier,
            requested_accelerator=model.requested_accelerator,
            requested_compute_node_id=model.requested_compute_node_id,
            swarm_join_material=dict(model.swarm_join_material or {}),
            required_labels={str(key): str(value) for key, value in dict(model.required_labels or {}).items()},
            expected_wireguard_ip=model.expected_wireguard_ip,
            expires_at=SellerOnboardingRepository._ensure_utc_datetime(model.expires_at),
            last_heartbeat_at=SellerOnboardingRepository._ensure_utc_datetime(model.last_heartbeat_at),
            created_at=SellerOnboardingRepository._ensure_utc_datetime(model.created_at),
            updated_at=SellerOnboardingRepository._ensure_utc_datetime(model.updated_at),
        )

    @staticmethod
    def _ensure_utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
