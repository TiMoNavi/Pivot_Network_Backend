"""create supply tables

Revision ID: 0003_create_supply_tables
Revises: 0002_create_phase1_core_tables
Create Date: 2026-04-05 01:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_create_supply_tables"
down_revision = "0002_create_phase1_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_user_id", sa.String(length=64), nullable=False),
        sa.Column("swarm_node_id", sa.String(length=64), nullable=False),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("tag", sa.String(length=128), nullable=False),
        sa.Column("digest", sa.String(length=255), nullable=True),
        sa.Column("registry", sa.String(length=255), nullable=False),
        sa.Column("base_image_ref", sa.String(length=255), nullable=True),
        sa.Column("runtime_contract_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'reported'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_image_artifacts_seller_user_id", "image_artifacts", ["seller_user_id"], unique=False)
    op.create_index("ix_image_artifacts_swarm_node_id", "image_artifacts", ["swarm_node_id"], unique=False)

    op.create_table(
        "image_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_user_id", sa.String(length=64), nullable=False),
        sa.Column("swarm_node_id", sa.String(length=64), nullable=False),
        sa.Column("image_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_image_ref", sa.String(length=512), nullable=False),
        sa.Column("offer_status", sa.String(length=32), server_default=sa.text("'reported'"), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=True),
        sa.Column("validation_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shell_agent_status", sa.String(length=32), nullable=True),
        sa.Column("runtime_contract_version", sa.String(length=64), nullable=True),
        sa.Column("probe_status", sa.String(length=32), nullable=True),
        sa.Column("probe_measured_capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("current_billable_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("pricing_error", sa.Text(), nullable=True),
        sa.Column("last_probed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["image_artifact_id"], ["image_artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_image_offers_seller_user_id", "image_offers", ["seller_user_id"], unique=False)
    op.create_index("ix_image_offers_swarm_node_id", "image_offers", ["swarm_node_id"], unique=False)
    op.create_index("ix_image_offers_offer_status", "image_offers", ["offer_status"], unique=False)

    op.create_table(
        "offer_price_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billable_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("price_components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["offer_id"], ["image_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offer_price_snapshots_offer_id", "offer_price_snapshots", ["offer_id"], unique=False)

    op.create_table(
        "node_capability_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("swarm_node_id", sa.String(length=64), nullable=False),
        sa.Column("cpu_logical", sa.Integer(), nullable=True),
        sa.Column("memory_total_mb", sa.Integer(), nullable=True),
        sa.Column("gpu_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("probe_source", sa.String(length=64), nullable=True),
        sa.Column("probed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_node_capability_snapshots_swarm_node_id", "node_capability_snapshots", ["swarm_node_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_node_capability_snapshots_swarm_node_id", table_name="node_capability_snapshots")
    op.drop_table("node_capability_snapshots")

    op.drop_index("ix_offer_price_snapshots_offer_id", table_name="offer_price_snapshots")
    op.drop_table("offer_price_snapshots")

    op.drop_index("ix_image_offers_offer_status", table_name="image_offers")
    op.drop_index("ix_image_offers_swarm_node_id", table_name="image_offers")
    op.drop_index("ix_image_offers_seller_user_id", table_name="image_offers")
    op.drop_table("image_offers")

    op.drop_index("ix_image_artifacts_swarm_node_id", table_name="image_artifacts")
    op.drop_index("ix_image_artifacts_seller_user_id", table_name="image_artifacts")
    op.drop_table("image_artifacts")
