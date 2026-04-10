"""create auth and trade core tables

Revision ID: 0002_auth_trade_core
Revises: 0001_norm_seller_onboarding
Create Date: 2026-04-10 23:30:00
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "0002_auth_trade_core"
down_revision = "0001_norm_seller_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("display_name", sa.String(length=100), nullable=False),
            sa.Column("password_salt", sa.String(length=64), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_role", "users", ["role"], unique=False)
        op.create_index("ix_users_status", "users", ["status"], unique=False)

    if "auth_sessions" not in existing_tables:
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("token", sa.Text(), nullable=False),
            sa.Column("scope", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
        op.create_index("ix_auth_sessions_token", "auth_sessions", ["token"], unique=True)
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], unique=False)
        op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"], unique=False)

    if "offers" not in existing_tables:
        op.create_table(
            "offers",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("seller_user_id", sa.String(length=64), nullable=False),
            sa.Column("seller_node_id", sa.String(length=128), nullable=False),
            sa.Column("offer_profile_id", sa.String(length=128), nullable=False),
            sa.Column("runtime_image_ref", sa.String(length=255), nullable=False),
            sa.Column("price_snapshot", sa.JSON(), nullable=False),
            sa.Column("capability_summary", sa.JSON(), nullable=False),
            sa.Column("inventory_state", sa.JSON(), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_offers_status", "offers", ["status"], unique=False)
        op.create_index("ix_offers_seller_user_id", "offers", ["seller_user_id"], unique=False)

    if "orders" not in existing_tables:
        op.create_table(
            "orders",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("buyer_user_id", sa.String(length=64), nullable=False),
            sa.Column("offer_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("requested_duration_minutes", sa.Integer(), nullable=False),
            sa.Column("price_snapshot", sa.JSON(), nullable=False),
            sa.Column("runtime_bundle_status", sa.String(length=64), nullable=True),
            sa.Column("access_grant_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_orders_buyer_user_id", "orders", ["buyer_user_id"], unique=False)
        op.create_index("ix_orders_offer_id", "orders", ["offer_id"], unique=False)
        op.create_index("ix_orders_status", "orders", ["status"], unique=False)
        op.create_index("ix_orders_access_grant_id", "orders", ["access_grant_id"], unique=False)

    if "access_grants" not in existing_tables:
        op.create_table(
            "access_grants",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("buyer_user_id", sa.String(length=64), nullable=False),
            sa.Column("order_id", sa.String(length=64), nullable=False),
            sa.Column("runtime_session_id", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("grant_type", sa.String(length=64), nullable=False),
            sa.Column("connect_material_payload", sa.JSON(), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_access_grants_buyer_user_id", "access_grants", ["buyer_user_id"], unique=False)
        op.create_index("ix_access_grants_order_id", "access_grants", ["order_id"], unique=False)
        op.create_index("ix_access_grants_status", "access_grants", ["status"], unique=False)
        op.create_index("ix_access_grants_expires_at", "access_grants", ["expires_at"], unique=False)

    _seed_offers(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "access_grants" in existing_tables:
        op.drop_index("ix_access_grants_expires_at", table_name="access_grants")
        op.drop_index("ix_access_grants_status", table_name="access_grants")
        op.drop_index("ix_access_grants_order_id", table_name="access_grants")
        op.drop_index("ix_access_grants_buyer_user_id", table_name="access_grants")
        op.drop_table("access_grants")

    if "orders" in existing_tables:
        op.drop_index("ix_orders_access_grant_id", table_name="orders")
        op.drop_index("ix_orders_status", table_name="orders")
        op.drop_index("ix_orders_offer_id", table_name="orders")
        op.drop_index("ix_orders_buyer_user_id", table_name="orders")
        op.drop_table("orders")

    if "offers" in existing_tables:
        op.drop_index("ix_offers_seller_user_id", table_name="offers")
        op.drop_index("ix_offers_status", table_name="offers")
        op.drop_table("offers")

    if "auth_sessions" in existing_tables:
        op.drop_index("ix_auth_sessions_revoked_at", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_token", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
        op.drop_table("auth_sessions")

    if "users" in existing_tables:
        op.drop_index("ix_users_status", table_name="users")
        op.drop_index("ix_users_role", table_name="users")
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")


def _seed_offers(bind) -> None:
    offers = sa.table(
        "offers",
        sa.column("id", sa.String()),
        sa.column("title", sa.String()),
        sa.column("status", sa.String()),
        sa.column("seller_user_id", sa.String()),
        sa.column("seller_node_id", sa.String()),
        sa.column("offer_profile_id", sa.String()),
        sa.column("runtime_image_ref", sa.String()),
        sa.column("price_snapshot", sa.JSON()),
        sa.column("capability_summary", sa.JSON()),
        sa.column("inventory_state", sa.JSON()),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing = bind.execute(sa.select(sa.func.count()).select_from(offers)).scalar_one()
    if existing:
        return
    now = datetime.now(UTC)
    bind.execute(
        offers.insert(),
        [
            {
                "id": "offer-medium-gpu",
                "title": "Medium GPU Runtime",
                "status": "listed",
                "seller_user_id": "seed-seller-1",
                "seller_node_id": "seed-node-1",
                "offer_profile_id": "profile-medium-gpu",
                "runtime_image_ref": "registry.example.com/pivot/runtime:python-gpu-v1",
                "price_snapshot": {"currency": "CNY", "hourly_price": 12.5},
                "capability_summary": {"cpu_limit": 8, "memory_limit_gb": 32, "gpu_mode": "shared"},
                "inventory_state": {"available": True, "reason": None},
                "published_at": now,
                "updated_at": now,
            },
            {
                "id": "offer-small-cpu",
                "title": "Small CPU Runtime",
                "status": "listed",
                "seller_user_id": "seed-seller-2",
                "seller_node_id": "seed-node-2",
                "offer_profile_id": "profile-small-cpu",
                "runtime_image_ref": "registry.example.com/pivot/runtime:python-cpu-v1",
                "price_snapshot": {"currency": "CNY", "hourly_price": 4.0},
                "capability_summary": {"cpu_limit": 2, "memory_limit_gb": 8, "gpu_mode": None},
                "inventory_state": {"available": True, "reason": None},
                "published_at": now,
                "updated_at": now,
            },
        ],
    )
