from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True)
    seller_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    node_key = Column(String(255), unique=True, index=True, nullable=False)
    device_fingerprint = Column(String(255), index=True, nullable=False)
    hostname = Column(String(255), nullable=False)
    system = Column(String(100), nullable=False)
    machine = Column(String(100), nullable=False)
    status = Column(String(50), default="available", nullable=False)
    shared_percent_preference = Column(Integer, default=10, nullable=False)
    node_class = Column(String(100), nullable=True)
    capabilities = Column(JSON, default=dict, nullable=False)
    seller_intent = Column(Text, nullable=True)
    docker_status = Column(String(100), nullable=True)
    swarm_state = Column(String(100), nullable=True)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    images = relationship(
        "ImageArtifact",
        back_populates="node",
        cascade="all, delete-orphan",
    )


class ImageArtifact(Base):
    __tablename__ = "image_artifacts"

    id = Column(Integer, primary_key=True)
    seller_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=True, index=True)
    repository = Column(String(255), nullable=False)
    tag = Column(String(255), nullable=False)
    digest = Column(String(255), nullable=True)
    registry = Column(String(255), nullable=False)
    source_image = Column(String(255), nullable=True)
    status = Column(String(50), default="uploaded", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    node = relationship("Node", back_populates="images")


class PriceFeedSnapshot(Base):
    __tablename__ = "price_feed_snapshots"

    id = Column(Integer, primary_key=True)
    provider = Column(String(50), index=True, nullable=False)
    reference_region = Column(String(100), nullable=False)
    status = Column(String(50), default="success", nullable=False)
    source_url = Column(String(1000), nullable=False)
    raw_payload = Column(JSON, default=dict, nullable=False)
    error_message = Column(Text, nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ResourceRateCard(Base):
    __tablename__ = "resource_rate_cards"

    id = Column(Integer, primary_key=True)
    status = Column(String(50), default="active", nullable=False)
    effective_hour = Column(DateTime(timezone=True), index=True, nullable=False)
    usd_cny_rate = Column(Float, nullable=False)
    cpu_price_usd_per_hour = Column(Float, nullable=False)
    ram_price_usd_per_gib_hour = Column(Float, nullable=False)
    gpu_price_usd_per_hour = Column(JSON, default=dict, nullable=False)
    source_summary = Column(JSON, default=dict, nullable=False)
    stale_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ImageOffer(Base):
    __tablename__ = "image_offers"

    id = Column(Integer, primary_key=True)
    seller_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    node_id = Column(Integer, ForeignKey("nodes.id"), index=True, nullable=False)
    image_artifact_id = Column(Integer, ForeignKey("image_artifacts.id"), index=True, nullable=False)
    repository = Column(String(255), nullable=False)
    tag = Column(String(255), nullable=False)
    digest = Column(String(255), nullable=True)
    runtime_image_ref = Column(String(500), nullable=False)
    offer_status = Column(String(50), default="draft", nullable=False)
    probe_status = Column(String(50), default="pending", nullable=False)
    probe_measured_capabilities = Column(JSON, default=dict, nullable=False)
    pricing_error = Column(Text, nullable=True)
    current_reference_price_cny_per_hour = Column(Float, nullable=True)
    current_billable_price_cny_per_hour = Column(Float, nullable=True)
    current_price_snapshot_id = Column(Integer, nullable=True, index=True)
    last_probed_at = Column(DateTime(timezone=True), nullable=True)
    last_priced_at = Column(DateTime(timezone=True), nullable=True)
    pricing_stale_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ImageOfferPriceSnapshot(Base):
    __tablename__ = "image_offer_price_snapshots"

    id = Column(Integer, primary_key=True)
    offer_id = Column(Integer, ForeignKey("image_offers.id"), index=True, nullable=False)
    resource_rate_card_id = Column(Integer, ForeignKey("resource_rate_cards.id"), index=True, nullable=False)
    effective_hour = Column(DateTime(timezone=True), index=True, nullable=False)
    reference_price_cny_per_hour = Column(Float, nullable=False)
    billable_price_cny_per_hour = Column(Float, nullable=False)
    price_components = Column(JSON, default=dict, nullable=False)
    probe_measured_capabilities = Column(JSON, default=dict, nullable=False)
    stale_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BuyerWallet(Base):
    __tablename__ = "buyer_wallets"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)
    balance_cny_credits = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    buyer = relationship("User", back_populates="buyer_wallet")


class UsageCharge(Base):
    __tablename__ = "usage_charges"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(Integer, ForeignKey("runtime_access_sessions.id"), index=True, nullable=False)
    offer_id = Column(Integer, ForeignKey("image_offers.id"), index=True, nullable=False)
    price_snapshot_id = Column(Integer, ForeignKey("image_offer_price_snapshots.id"), nullable=True, index=True)
    billing_hour_start = Column(DateTime(timezone=True), nullable=False)
    billing_hour_end = Column(DateTime(timezone=True), nullable=False)
    hourly_price_cny = Column(Float, nullable=False)
    charged_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    ledger_id = Column(Integer, nullable=True, index=True)


class WalletLedger(Base):
    __tablename__ = "wallet_ledgers"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(Integer, ForeignKey("runtime_access_sessions.id"), nullable=True, index=True)
    usage_charge_id = Column(Integer, ForeignKey("usage_charges.id"), nullable=True, index=True)
    entry_type = Column(String(50), nullable=False)
    amount_delta_cny = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    detail = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BuyerOrder(Base):
    __tablename__ = "buyer_orders"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    offer_id = Column(Integer, ForeignKey("image_offers.id"), index=True, nullable=False)
    requested_duration_minutes = Column(Integer, nullable=False)
    issued_hourly_price_cny = Column(Float, nullable=False)
    order_status = Column(String(50), default="issued", nullable=False)
    license_token = Column(String(255), unique=True, index=True, nullable=False)
    license_redeemed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class RuntimeAccessSession(Base):
    __tablename__ = "runtime_access_sessions"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    seller_node_id = Column(Integer, ForeignKey("nodes.id"), index=True, nullable=False)
    image_artifact_id = Column(Integer, ForeignKey("image_artifacts.id"), nullable=True, index=True)
    image_offer_id = Column(Integer, ForeignKey("image_offers.id"), nullable=True, index=True)
    runtime_image = Column(String(255), nullable=False)
    source_type = Column(String(50), default="inline_code", nullable=False)
    source_ref = Column(String(500), nullable=True)
    working_dir = Column(String(255), nullable=True)
    code_filename = Column(String(255), nullable=False)
    code_sha256 = Column(String(128), nullable=False)
    service_name = Column(String(255), unique=True, index=True, nullable=False)
    config_name = Column(String(255), unique=True, index=True, nullable=False)
    connect_code = Column(String(255), unique=True, index=True, nullable=False)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    network_mode = Column(String(50), default="wireguard", nullable=False)
    buyer_wireguard_public_key = Column(String(255), nullable=True)
    buyer_wireguard_client_address = Column(String(100), nullable=True)
    seller_wireguard_target = Column(String(100), nullable=True)
    status = Column(String(50), default="created", nullable=False)
    command = Column(JSON, default=list, nullable=False)
    last_logs = Column(Text, nullable=True)
    billed_through = Column(DateTime(timezone=True), nullable=True)
    accrued_usage_cny = Column(Float, default=0.0, nullable=False)
    last_hourly_price_cny = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
