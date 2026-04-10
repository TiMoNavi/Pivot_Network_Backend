"""create phase1 core tables

Revision ID: 0002_create_phase1_core_tables
Revises: 0001_create_users_table
Create Date: 2026-04-05 00:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_create_phase1_core_tables"
down_revision = "0001_create_users_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=64), server_default=sa.text("'api_access'"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_tokens_token_hash", "session_tokens", ["token_hash"], unique=True)
    op.create_index("ix_session_tokens_user_id", "session_tokens", ["user_id"], unique=False)
    op.create_index("ix_session_tokens_expires_at", "session_tokens", ["expires_at"], unique=False)

    op.create_table(
        "seller_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "buyer_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "swarm_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_key", sa.String(length=64), nullable=False),
        sa.Column("adapter_base_url", sa.String(length=255), nullable=False),
        sa.Column("manager_host", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_swarm_clusters_cluster_key", "swarm_clusters", ["cluster_key"], unique=True)
    op.create_index("ix_swarm_clusters_last_synced_at", "swarm_clusters", ["last_synced_at"], unique=False)

    op.create_table(
        "swarm_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("swarm_node_id", sa.String(length=64), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("availability", sa.String(length=32), nullable=False),
        sa.Column("platform_role", sa.String(length=64), nullable=True),
        sa.Column("compute_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("compute_node_id", sa.String(length=128), nullable=True),
        sa.Column("seller_user_id", sa.String(length=64), nullable=True),
        sa.Column("accelerator", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["cluster_id"], ["swarm_clusters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_swarm_nodes_swarm_node_id", "swarm_nodes", ["swarm_node_id"], unique=True)
    op.create_index("ix_swarm_nodes_hostname", "swarm_nodes", ["hostname"], unique=False)
    op.create_index("ix_swarm_nodes_status", "swarm_nodes", ["status"], unique=False)
    op.create_index("ix_swarm_nodes_compute_node_id", "swarm_nodes", ["compute_node_id"], unique=False)
    op.create_index("ix_swarm_nodes_seller_user_id", "swarm_nodes", ["seller_user_id"], unique=False)
    op.create_index("ix_swarm_nodes_last_seen_at", "swarm_nodes", ["last_seen_at"], unique=False)

    op.create_table(
        "swarm_node_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_key", sa.String(length=255), nullable=False),
        sa.Column("label_value", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["swarm_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "label_key", name="uq_swarm_node_labels_node_key"),
    )
    op.create_index("ix_swarm_node_labels_node_id", "swarm_node_labels", ["node_id"], unique=False)

    op.create_table(
        "swarm_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("swarm_service_id", sa.String(length=64), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("service_kind", sa.String(length=32), server_default=sa.text("'other'"), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("image", sa.String(length=512), nullable=False),
        sa.Column("desired_replicas", sa.Integer(), nullable=True),
        sa.Column("running_replicas", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("seller_node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("runtime_session_id", sa.String(length=128), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["cluster_id"], ["swarm_clusters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_node_id"], ["swarm_nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_swarm_services_swarm_service_id", "swarm_services", ["swarm_service_id"], unique=True)
    op.create_index("ix_swarm_services_service_name", "swarm_services", ["service_name"], unique=False)
    op.create_index("ix_swarm_services_status", "swarm_services", ["status"], unique=False)
    op.create_index("ix_swarm_services_runtime_session_id", "swarm_services", ["runtime_session_id"], unique=False)
    op.create_index("ix_swarm_services_last_synced_at", "swarm_services", ["last_synced_at"], unique=False)

    op.create_table(
        "swarm_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("swarm_task_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("desired_state", sa.String(length=64), nullable=False),
        sa.Column("current_state", sa.String(length=255), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("container_id", sa.String(length=128), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["swarm_services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["swarm_nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_swarm_tasks_swarm_task_id", "swarm_tasks", ["swarm_task_id"], unique=True)
    op.create_index("ix_swarm_tasks_node_id", "swarm_tasks", ["node_id"], unique=False)
    op.create_index("ix_swarm_tasks_last_synced_at", "swarm_tasks", ["last_synced_at"], unique=False)

    op.create_table(
        "swarm_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_scope", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("nodes_changed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("services_changed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tasks_changed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_swarm_sync_runs_started_at", "swarm_sync_runs", ["started_at"], unique=False)
    op.create_index("ix_swarm_sync_runs_status", "swarm_sync_runs", ["status"], unique=False)

    op.create_table(
        "swarm_sync_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_key", sa.String(length=255), nullable=False),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("before_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sync_run_id"], ["swarm_sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_swarm_sync_events_entity_key", "swarm_sync_events", ["entity_key"], unique=False)
    op.create_index("ix_swarm_sync_events_sync_run_id", "swarm_sync_events", ["sync_run_id"], unique=False)

    op.create_table(
        "activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_events_event_type", "activity_events", ["event_type"], unique=False)
    op.create_index("ix_activity_events_actor_user_id", "activity_events", ["actor_user_id"], unique=False)
    op.create_index("ix_activity_events_target_id", "activity_events", ["target_id"], unique=False)

    op.create_table(
        "operation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_key", sa.String(length=255), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operation_logs_operation_type", "operation_logs", ["operation_type"], unique=False)
    op.create_index("ix_operation_logs_target_key", "operation_logs", ["target_key"], unique=False)
    op.create_index("ix_operation_logs_status", "operation_logs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_operation_logs_status", table_name="operation_logs")
    op.drop_index("ix_operation_logs_target_key", table_name="operation_logs")
    op.drop_index("ix_operation_logs_operation_type", table_name="operation_logs")
    op.drop_table("operation_logs")

    op.drop_index("ix_activity_events_target_id", table_name="activity_events")
    op.drop_index("ix_activity_events_actor_user_id", table_name="activity_events")
    op.drop_index("ix_activity_events_event_type", table_name="activity_events")
    op.drop_table("activity_events")

    op.drop_index("ix_swarm_sync_events_sync_run_id", table_name="swarm_sync_events")
    op.drop_index("ix_swarm_sync_events_entity_key", table_name="swarm_sync_events")
    op.drop_table("swarm_sync_events")

    op.drop_index("ix_swarm_sync_runs_status", table_name="swarm_sync_runs")
    op.drop_index("ix_swarm_sync_runs_started_at", table_name="swarm_sync_runs")
    op.drop_table("swarm_sync_runs")

    op.drop_index("ix_swarm_tasks_last_synced_at", table_name="swarm_tasks")
    op.drop_index("ix_swarm_tasks_node_id", table_name="swarm_tasks")
    op.drop_index("ix_swarm_tasks_swarm_task_id", table_name="swarm_tasks")
    op.drop_table("swarm_tasks")

    op.drop_index("ix_swarm_services_last_synced_at", table_name="swarm_services")
    op.drop_index("ix_swarm_services_runtime_session_id", table_name="swarm_services")
    op.drop_index("ix_swarm_services_status", table_name="swarm_services")
    op.drop_index("ix_swarm_services_service_name", table_name="swarm_services")
    op.drop_index("ix_swarm_services_swarm_service_id", table_name="swarm_services")
    op.drop_table("swarm_services")

    op.drop_index("ix_swarm_node_labels_node_id", table_name="swarm_node_labels")
    op.drop_table("swarm_node_labels")

    op.drop_index("ix_swarm_nodes_last_seen_at", table_name="swarm_nodes")
    op.drop_index("ix_swarm_nodes_seller_user_id", table_name="swarm_nodes")
    op.drop_index("ix_swarm_nodes_compute_node_id", table_name="swarm_nodes")
    op.drop_index("ix_swarm_nodes_status", table_name="swarm_nodes")
    op.drop_index("ix_swarm_nodes_hostname", table_name="swarm_nodes")
    op.drop_index("ix_swarm_nodes_swarm_node_id", table_name="swarm_nodes")
    op.drop_table("swarm_nodes")

    op.drop_index("ix_swarm_clusters_last_synced_at", table_name="swarm_clusters")
    op.drop_index("ix_swarm_clusters_cluster_key", table_name="swarm_clusters")
    op.drop_table("swarm_clusters")

    op.drop_table("buyer_profiles")
    op.drop_table("seller_profiles")

    op.drop_index("ix_session_tokens_expires_at", table_name="session_tokens")
    op.drop_index("ix_session_tokens_user_id", table_name="session_tokens")
    op.drop_index("ix_session_tokens_token_hash", table_name="session_tokens")
    op.drop_table("session_tokens")
