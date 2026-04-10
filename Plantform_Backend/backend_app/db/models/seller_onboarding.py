from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend_app.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SellerOnboardingSessionModel(Base):
    __tablename__ = "seller_onboarding_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    one_time_token: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_offer_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requested_accelerator: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_compute_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    swarm_join_material: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    required_labels: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expected_wireguard_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )


class SellerOnboardingLinuxHostProbeModel(Base):
    __tablename__ = "seller_onboarding_linux_host_probes"

    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reported_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    host_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    os_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    distribution_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kernel_release: Mapped[str | None] = mapped_column(String(128), nullable=True)
    virtualization_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sudo_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    observed_ips: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SellerOnboardingLinuxSubstrateProbeModel(Base):
    __tablename__ = "seller_onboarding_linux_substrate_probes"

    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reported_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    distribution_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kernel_release: Mapped[str | None] = mapped_column(String(128), nullable=True)
    docker_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    docker_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wireguard_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    gpu_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cpu_cores: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disk_free_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_ips: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    observed_wireguard_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_advertise_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_data_path_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SellerOnboardingContainerRuntimeProbeModel(Base):
    __tablename__ = "seller_onboarding_container_runtime_probes"

    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reported_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    runtime_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    engine_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    image_store_accessible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    network_ready: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    observed_images: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SellerOnboardingJoinCompleteModel(Base):
    __tablename__ = "seller_onboarding_join_completions"

    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reported_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    node_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    compute_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_wireguard_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_advertise_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_data_path_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SellerOnboardingCorrectionModel(Base):
    __tablename__ = "seller_onboarding_corrections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reported_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_surface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correction_action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_wireguard_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_advertise_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_data_path_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SellerOnboardingManagerAddressOverrideModel(Base):
    __tablename__ = "seller_onboarding_manager_address_overrides"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reported_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_surface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    override_target_addr: Mapped[str] = mapped_column(String(128), nullable=False)
    override_reason: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SellerOnboardingAuthoritativeEffectiveTargetModel(Base):
    __tablename__ = "seller_onboarding_authoritative_effective_targets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reported_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_surface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_target_addr: Mapped[str] = mapped_column(String(128), nullable=False)
    effective_target_reason: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SellerOnboardingManagerAcceptanceModel(Base):
    __tablename__ = "seller_onboarding_manager_acceptances"

    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expected_wireguard_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_manager_node_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    matched: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    node_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    compute_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SellerOnboardingManagerAcceptanceHistoryModel(Base):
    __tablename__ = "seller_onboarding_manager_acceptance_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expected_wireguard_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_manager_node_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    matched: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    node_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    compute_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SellerOnboardingMinimumTcpValidationModel(Base):
    __tablename__ = "seller_onboarding_minimum_tcp_validations"

    join_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("seller_onboarding_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seller_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reported_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(16), nullable=False)
    reachable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validated_against_manager_target: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validated_against_effective_target: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_target_addr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    effective_target_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    truth_authority: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
