"""create runtime session tables

Revision ID: 0005_runtime_session
Revises: 0004_create_buyer_trade_tables
Create Date: 2026-04-05 02:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_runtime_session"
down_revision = "0004_create_buyer_trade_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("buyer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_image_ref", sa.String(length=512), nullable=False),
        sa.Column("runtime_service_name", sa.String(length=255), nullable=True),
        sa.Column("gateway_service_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'created'"), nullable=False),
        sa.Column("gateway_host", sa.String(length=255), nullable=True),
        sa.Column("gateway_port", sa.Integer(), nullable=True),
        sa.Column("network_mode", sa.String(length=32), nullable=False),
        sa.Column("connect_material_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("connect_material_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["access_code_id"], ["access_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["buyer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["image_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["buyer_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_node_id"], ["swarm_nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_sessions_buyer_user_id", "runtime_sessions", ["buyer_user_id"], unique=False)
    op.create_index("ix_runtime_sessions_offer_id", "runtime_sessions", ["offer_id"], unique=False)
    op.create_index("ix_runtime_sessions_order_id", "runtime_sessions", ["order_id"], unique=False)
    op.create_index("ix_runtime_sessions_access_code_id", "runtime_sessions", ["access_code_id"], unique=False)
    op.create_index("ix_runtime_sessions_status", "runtime_sessions", ["status"], unique=False)
    op.create_index("ix_runtime_sessions_expires_at", "runtime_sessions", ["expires_at"], unique=False)
    op.create_index("ix_runtime_sessions_last_synced_at", "runtime_sessions", ["last_synced_at"], unique=False)

    op.create_table(
        "runtime_session_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["runtime_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_session_events_session_id", "runtime_session_events", ["session_id"], unique=False)
    op.create_index("ix_runtime_session_events_event_type", "runtime_session_events", ["event_type"], unique=False)

    op.create_table(
        "gateway_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol", sa.String(length=32), server_default=sa.text("'http'"), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("access_url", sa.String(length=512), nullable=False),
        sa.Column("path_prefix", sa.String(length=255), nullable=True),
        sa.Column("access_mode", sa.String(length=32), server_default=sa.text("'web_terminal'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'provisioning'"), nullable=False),
        sa.Column("connect_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["runtime_session_id"], ["runtime_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("runtime_session_id", name="uq_gateway_endpoints_runtime_session_id"),
    )
    op.create_index("ix_gateway_endpoints_runtime_session_id", "gateway_endpoints", ["runtime_session_id"], unique=False)

    op.create_table(
        "wireguard_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_type", sa.String(length=32), nullable=False),
        sa.Column("public_key", sa.String(length=128), nullable=True),
        sa.Column("server_public_key", sa.String(length=128), nullable=True),
        sa.Column("client_address", sa.String(length=64), nullable=True),
        sa.Column("endpoint_host", sa.String(length=255), nullable=True),
        sa.Column("endpoint_port", sa.Integer(), nullable=True),
        sa.Column("allowed_ips", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("persistent_keepalive", sa.Integer(), nullable=True),
        sa.Column("server_interface", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'requested'"), nullable=False),
        sa.Column("lease_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["runtime_session_id"], ["runtime_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("runtime_session_id", "lease_type", name="uq_wireguard_leases_session_type"),
    )
    op.create_index("ix_wireguard_leases_runtime_session_id", "wireguard_leases", ["runtime_session_id"], unique=False)
    op.create_index("ix_wireguard_leases_status", "wireguard_leases", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_wireguard_leases_status", table_name="wireguard_leases")
    op.drop_index("ix_wireguard_leases_runtime_session_id", table_name="wireguard_leases")
    op.drop_table("wireguard_leases")

    op.drop_index("ix_gateway_endpoints_runtime_session_id", table_name="gateway_endpoints")
    op.drop_table("gateway_endpoints")

    op.drop_index("ix_runtime_session_events_event_type", table_name="runtime_session_events")
    op.drop_index("ix_runtime_session_events_session_id", table_name="runtime_session_events")
    op.drop_table("runtime_session_events")

    op.drop_index("ix_runtime_sessions_last_synced_at", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_expires_at", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_status", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_access_code_id", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_order_id", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_offer_id", table_name="runtime_sessions")
    op.drop_index("ix_runtime_sessions_buyer_user_id", table_name="runtime_sessions")
    op.drop_table("runtime_sessions")
