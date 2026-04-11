"""add runtime sessions table

Revision ID: 0004_runtime_sessions
Revises: 0003_capability_assessments
Create Date: 2026-04-11 05:25:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_runtime_sessions"
down_revision = "0003_capability_assessments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "runtime_sessions" in existing_tables:
        return

    op.create_table(
        "runtime_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("access_grant_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("offer_id", sa.String(length=64), nullable=False),
        sa.Column("buyer_user_id", sa.String(length=64), nullable=False),
        sa.Column("seller_user_id", sa.String(length=64), nullable=True),
        sa.Column("compute_node_id", sa.String(length=128), nullable=True),
        sa.Column("source_join_session_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("runtime_bundle_status", sa.String(length=32), nullable=False),
        sa.Column("network_mode", sa.String(length=32), nullable=False),
        sa.Column("buyer_wireguard_public_key", sa.Text(), nullable=False),
        sa.Column("runtime_service_name", sa.String(length=128), nullable=True),
        sa.Column("gateway_service_name", sa.String(length=128), nullable=True),
        sa.Column("network_name", sa.String(length=128), nullable=True),
        sa.Column("connect_metadata", sa.JSON(), nullable=False),
        sa.Column("wireguard_lease_metadata", sa.JSON(), nullable=False),
        sa.Column("recent_error_summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ux_runtime_sessions_access_grant_id", "runtime_sessions", ["access_grant_id"], unique=True)
    op.create_index("ix_runtime_sessions_order_id", "runtime_sessions", ["order_id"], unique=False)
    op.create_index("ix_runtime_sessions_offer_id", "runtime_sessions", ["offer_id"], unique=False)
    op.create_index("ix_runtime_sessions_buyer_user_id", "runtime_sessions", ["buyer_user_id"], unique=False)
    op.create_index("ix_runtime_sessions_seller_user_id", "runtime_sessions", ["seller_user_id"], unique=False)
    op.create_index("ix_runtime_sessions_compute_node_id", "runtime_sessions", ["compute_node_id"], unique=False)
    op.create_index("ix_runtime_sessions_source_join_session_id", "runtime_sessions", ["source_join_session_id"], unique=False)
    op.create_index("ix_runtime_sessions_status", "runtime_sessions", ["status"], unique=False)
    op.create_index("ix_runtime_sessions_runtime_bundle_status", "runtime_sessions", ["runtime_bundle_status"], unique=False)
    op.create_index("ix_runtime_sessions_expires_at", "runtime_sessions", ["expires_at"], unique=False)
    op.create_index("ix_runtime_sessions_last_heartbeat_at", "runtime_sessions", ["last_heartbeat_at"], unique=False)
    op.create_index("ix_runtime_sessions_closed_at", "runtime_sessions", ["closed_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "runtime_sessions" not in existing_tables:
        return

    op.drop_index("ix_runtime_sessions_closed_at", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_last_heartbeat_at", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_expires_at", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_runtime_bundle_status", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_status", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_source_join_session_id", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_compute_node_id", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_seller_user_id", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_buyer_user_id", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_offer_id", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_order_id", table_name="runtime_sessions")
    op.drop_index("ux_runtime_sessions_access_grant_id", table_name="runtime_sessions")
    op.drop_table("runtime_sessions")
