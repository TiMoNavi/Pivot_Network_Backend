from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend_app.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )


class AuthSessionModel(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)


class OfferModel(Base):
    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    seller_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    seller_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    compute_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    offer_profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    runtime_image_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    price_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capability_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    inventory_state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_join_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_assessment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)


class SellerCapabilityAssessmentModel(Base):
    __tablename__ = "seller_capability_assessments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seller_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    onboarding_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    compute_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    node_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    assessment_status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_offer_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requested_accelerator: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sources_used: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    measured_capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    pricing_decision: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    runtime_image_validation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recommended_offer: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    apply_offer: Mapped[bool] = mapped_column(nullable=False, default=False)
    apply_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    buyer_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    offer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requested_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    runtime_bundle_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_grant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )


class AccessGrantModel(Base):
    __tablename__ = "access_grants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    buyer_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    runtime_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    grant_type: Mapped[str] = mapped_column(String(64), nullable=False)
    connect_material_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
