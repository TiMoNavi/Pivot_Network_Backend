"""create buyer trade tables

Revision ID: 0004_create_buyer_trade_tables
Revises: 0003_create_supply_tables
Create Date: 2026-04-05 01:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_create_buyer_trade_tables"
down_revision = "0003_create_supply_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buyer_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("buyer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("order_status", sa.String(length=32), server_default=sa.text("'created'"), nullable=False),
        sa.Column("issued_hourly_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("requested_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["buyer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["image_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_buyer_orders_order_no", "buyer_orders", ["order_no"], unique=True)
    op.create_index("ix_buyer_orders_buyer_user_id", "buyer_orders", ["buyer_user_id"], unique=False)
    op.create_index("ix_buyer_orders_offer_id", "buyer_orders", ["offer_id"], unique=False)
    op.create_index("ix_buyer_orders_order_status", "buyer_orders", ["order_status"], unique=False)

    op.create_table(
        "access_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("buyer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'issued'"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["buyer_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["buyer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_codes_access_code", "access_codes", ["access_code"], unique=True)
    op.create_index("ix_access_codes_buyer_user_id", "access_codes", ["buyer_user_id"], unique=False)
    op.create_index("ix_access_codes_order_id", "access_codes", ["order_id"], unique=False)
    op.create_index("ix_access_codes_status", "access_codes", ["status"], unique=False)
    op.create_index("ix_access_codes_expires_at", "access_codes", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_access_codes_expires_at", table_name="access_codes")
    op.drop_index("ix_access_codes_status", table_name="access_codes")
    op.drop_index("ix_access_codes_order_id", table_name="access_codes")
    op.drop_index("ix_access_codes_buyer_user_id", table_name="access_codes")
    op.drop_index("ix_access_codes_access_code", table_name="access_codes")
    op.drop_table("access_codes")

    op.drop_index("ix_buyer_orders_order_status", table_name="buyer_orders")
    op.drop_index("ix_buyer_orders_offer_id", table_name="buyer_orders")
    op.drop_index("ix_buyer_orders_buyer_user_id", table_name="buyer_orders")
    op.drop_index("ix_buyer_orders_order_no", table_name="buyer_orders")
    op.drop_table("buyer_orders")
