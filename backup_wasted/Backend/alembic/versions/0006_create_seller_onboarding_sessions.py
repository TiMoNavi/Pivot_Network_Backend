"""create seller onboarding sessions table

Revision ID: 0006_seller_onboarding_sessions
Revises: 0005_runtime_session
Create Date: 2026-04-05 15:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_seller_onboarding_sessions"
down_revision = "0005_runtime_session"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seller_onboarding_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
        sa.Column("requested_accelerator", sa.String(length=64), server_default=sa.text("'gpu'"), nullable=False),
        sa.Column("requested_compute_node_id", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_env_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["seller_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_seller_onboarding_sessions_seller_user_id",
        "seller_onboarding_sessions",
        ["seller_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_seller_onboarding_sessions_status",
        "seller_onboarding_sessions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_seller_onboarding_sessions_expires_at",
        "seller_onboarding_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_seller_onboarding_sessions_last_heartbeat_at",
        "seller_onboarding_sessions",
        ["last_heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_seller_onboarding_sessions_last_heartbeat_at", table_name="seller_onboarding_sessions")
    op.drop_index("ix_seller_onboarding_sessions_expires_at", table_name="seller_onboarding_sessions")
    op.drop_index("ix_seller_onboarding_sessions_status", table_name="seller_onboarding_sessions")
    op.drop_index("ix_seller_onboarding_sessions_seller_user_id", table_name="seller_onboarding_sessions")
    op.drop_table("seller_onboarding_sessions")
