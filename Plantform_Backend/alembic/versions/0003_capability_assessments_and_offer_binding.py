"""add capability assessments and offer binding columns

Revision ID: 0003_capability_assessments
Revises: 0002_auth_trade_core
Create Date: 2026-04-10 23:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_capability_assessments"
down_revision = "0002_auth_trade_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seller_capability_assessments" not in existing_tables:
        op.create_table(
            "seller_capability_assessments",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("seller_user_id", sa.String(length=64), nullable=False),
            sa.Column("onboarding_session_id", sa.String(length=64), nullable=True),
            sa.Column("compute_node_id", sa.String(length=128), nullable=True),
            sa.Column("node_ref", sa.String(length=128), nullable=True),
            sa.Column("assessment_status", sa.String(length=64), nullable=False),
            sa.Column("requested_offer_tier", sa.String(length=32), nullable=True),
            sa.Column("requested_accelerator", sa.String(length=32), nullable=True),
            sa.Column("request_snapshot", sa.JSON(), nullable=False),
            sa.Column("sources_used", sa.JSON(), nullable=False),
            sa.Column("measured_capabilities", sa.JSON(), nullable=False),
            sa.Column("pricing_decision", sa.JSON(), nullable=False),
            sa.Column("runtime_image_validation", sa.JSON(), nullable=False),
            sa.Column("recommended_offer", sa.JSON(), nullable=False),
            sa.Column("warnings", sa.JSON(), nullable=False),
            sa.Column("apply_offer", sa.Boolean(), nullable=False),
            sa.Column("apply_result", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_seller_capability_assessments_seller_user_id",
            "seller_capability_assessments",
            ["seller_user_id"],
            unique=False,
        )
        op.create_index(
            "ix_seller_capability_assessments_onboarding_session_id",
            "seller_capability_assessments",
            ["onboarding_session_id"],
            unique=False,
        )
        op.create_index(
            "ix_seller_capability_assessments_compute_node_id",
            "seller_capability_assessments",
            ["compute_node_id"],
            unique=False,
        )
        op.create_index(
            "ix_seller_capability_assessments_assessment_status",
            "seller_capability_assessments",
            ["assessment_status"],
            unique=False,
        )

    if "offers" in existing_tables:
        existing_columns = {column["name"] for column in inspector.get_columns("offers")}
        if "compute_node_id" not in existing_columns:
            op.add_column("offers", sa.Column("compute_node_id", sa.String(length=128), nullable=True))
        if "source_join_session_id" not in existing_columns:
            op.add_column("offers", sa.Column("source_join_session_id", sa.String(length=64), nullable=True))
        if "source_assessment_id" not in existing_columns:
            op.add_column("offers", sa.Column("source_assessment_id", sa.String(length=64), nullable=True))

        existing_indexes = {index["name"] for index in inspector.get_indexes("offers")}
        if "ux_offers_compute_node_id" not in existing_indexes:
            op.create_index("ux_offers_compute_node_id", "offers", ["compute_node_id"], unique=True)

        offers = sa.table("offers", sa.column("id", sa.String()))
        bind.execute(
            offers.delete().where(offers.c.id.in_(("offer-medium-gpu", "offer-small-cpu")))
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "offers" in existing_tables:
        existing_indexes = {index["name"] for index in inspector.get_indexes("offers")}
        with op.batch_alter_table("offers") as batch_op:
            if "ux_offers_compute_node_id" in existing_indexes:
                batch_op.drop_index("ux_offers_compute_node_id")
            existing_columns = {column["name"] for column in inspector.get_columns("offers")}
            if "source_assessment_id" in existing_columns:
                batch_op.drop_column("source_assessment_id")
            if "source_join_session_id" in existing_columns:
                batch_op.drop_column("source_join_session_id")
            if "compute_node_id" in existing_columns:
                batch_op.drop_column("compute_node_id")

    if "seller_capability_assessments" in existing_tables:
        op.drop_index(
            "ix_seller_capability_assessments_assessment_status",
            table_name="seller_capability_assessments",
        )
        op.drop_index(
            "ix_seller_capability_assessments_compute_node_id",
            table_name="seller_capability_assessments",
        )
        op.drop_index(
            "ix_seller_capability_assessments_onboarding_session_id",
            table_name="seller_capability_assessments",
        )
        op.drop_index(
            "ix_seller_capability_assessments_seller_user_id",
            table_name="seller_capability_assessments",
        )
        op.drop_table("seller_capability_assessments")
