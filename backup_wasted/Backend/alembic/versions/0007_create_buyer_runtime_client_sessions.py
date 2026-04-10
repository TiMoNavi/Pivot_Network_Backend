"""create buyer runtime client sessions

Revision ID: 0007_buyer_client
Revises: 0006_seller_onboarding_sessions
Create Date: 2026-04-06 16:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

revision = "0007_buyer_client"
down_revision = "0006_seller_onboarding_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("buyer_runtime_client_sessions"):
        op.create_table(
            "buyer_runtime_client_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("runtime_session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("buyer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_env_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["runtime_session_id"], ["runtime_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["buyer_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("runtime_session_id", name="uq_buyer_runtime_client_sessions_runtime_session_id"),
        )

    indexes = {index["name"] for index in inspector.get_indexes("buyer_runtime_client_sessions")}
    if "ix_buyer_runtime_client_sessions_runtime_session_id" not in indexes:
        op.create_index(
            "ix_buyer_runtime_client_sessions_runtime_session_id",
            "buyer_runtime_client_sessions",
            ["runtime_session_id"],
            unique=False,
        )
    if "ix_buyer_runtime_client_sessions_buyer_user_id" not in indexes:
        op.create_index(
            "ix_buyer_runtime_client_sessions_buyer_user_id",
            "buyer_runtime_client_sessions",
            ["buyer_user_id"],
            unique=False,
        )
    if "ix_buyer_runtime_client_sessions_status" not in indexes:
        op.create_index(
            "ix_buyer_runtime_client_sessions_status",
            "buyer_runtime_client_sessions",
            ["status"],
            unique=False,
        )
    if "ix_buyer_runtime_client_sessions_expires_at" not in indexes:
        op.create_index(
            "ix_buyer_runtime_client_sessions_expires_at",
            "buyer_runtime_client_sessions",
            ["expires_at"],
            unique=False,
        )
    if "ix_buyer_runtime_client_sessions_last_heartbeat_at" not in indexes:
        op.create_index(
            "ix_buyer_runtime_client_sessions_last_heartbeat_at",
            "buyer_runtime_client_sessions",
            ["last_heartbeat_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_buyer_runtime_client_sessions_last_heartbeat_at", table_name="buyer_runtime_client_sessions")
    op.drop_index("ix_buyer_runtime_client_sessions_expires_at", table_name="buyer_runtime_client_sessions")
    op.drop_index("ix_buyer_runtime_client_sessions_status", table_name="buyer_runtime_client_sessions")
    op.drop_index("ix_buyer_runtime_client_sessions_buyer_user_id", table_name="buyer_runtime_client_sessions")
    op.drop_index("ix_buyer_runtime_client_sessions_runtime_session_id", table_name="buyer_runtime_client_sessions")
    op.drop_table("buyer_runtime_client_sessions")
