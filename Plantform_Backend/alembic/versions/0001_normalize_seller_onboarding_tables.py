"""normalize seller onboarding tables

Revision ID: 0001_norm_seller_onboarding
Revises:
Create Date: 2026-04-10 22:00:00
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "0001_norm_seller_onboarding"
down_revision = None
branch_labels = None
depends_on = None

SESSION_TABLE = "seller_onboarding_sessions"
LEGACY_JSON_COLUMNS = {
    "linux_host_probe",
    "linux_substrate_probe",
    "container_runtime_probe",
    "join_complete",
    "corrections",
    "manager_address_override",
    "authoritative_effective_target",
    "manager_acceptance",
    "manager_acceptance_history",
    "minimum_tcp_validation",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if SESSION_TABLE not in existing_tables:
        _create_session_table()
        existing_tables.add(SESSION_TABLE)

    _create_normalized_tables(existing_tables)

    legacy_columns = set()
    if SESSION_TABLE in existing_tables:
        legacy_columns = {
            column["name"]
            for column in inspector.get_columns(SESSION_TABLE)
            if column["name"] in LEGACY_JSON_COLUMNS
        }

    if legacy_columns:
        _migrate_legacy_json_payloads(bind, legacy_columns)
        with op.batch_alter_table(SESSION_TABLE) as batch_op:
            for column_name in sorted(legacy_columns):
                batch_op.drop_column(column_name)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if SESSION_TABLE in existing_tables:
        current_columns = {column["name"] for column in inspector.get_columns(SESSION_TABLE)}
        missing_legacy = LEGACY_JSON_COLUMNS - current_columns
        if missing_legacy:
            with op.batch_alter_table(SESSION_TABLE) as batch_op:
                for column_name in sorted(missing_legacy):
                    batch_op.add_column(sa.Column(column_name, sa.JSON(), nullable=True))
            _rebuild_legacy_json_payloads(bind)

    for table_name in [
        "seller_onboarding_minimum_tcp_validations",
        "seller_onboarding_manager_acceptance_history",
        "seller_onboarding_manager_acceptances",
        "seller_onboarding_authoritative_effective_targets",
        "seller_onboarding_manager_address_overrides",
        "seller_onboarding_corrections",
        "seller_onboarding_join_completions",
        "seller_onboarding_container_runtime_probes",
        "seller_onboarding_linux_substrate_probes",
        "seller_onboarding_linux_host_probes",
    ]:
        if table_name in existing_tables:
            op.drop_table(table_name)


def _create_session_table() -> None:
    op.create_table(
        SESSION_TABLE,
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("seller_user_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("one_time_token", sa.String(length=255), nullable=False),
        sa.Column("requested_offer_tier", sa.String(length=32), nullable=True),
        sa.Column("requested_accelerator", sa.String(length=32), nullable=False),
        sa.Column("requested_compute_node_id", sa.String(length=128), nullable=True),
        sa.Column("swarm_join_material", sa.JSON(), nullable=False),
        sa.Column("required_labels", sa.JSON(), nullable=False),
        sa.Column("expected_wireguard_ip", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_seller_onboarding_sessions_seller_user_id", SESSION_TABLE, ["seller_user_id"], unique=False)
    op.create_index("ix_seller_onboarding_sessions_status", SESSION_TABLE, ["status"], unique=False)
    op.create_index("ix_seller_onboarding_sessions_expires_at", SESSION_TABLE, ["expires_at"], unique=False)
    op.create_index(
        "ix_seller_onboarding_sessions_last_heartbeat_at",
        SESSION_TABLE,
        ["last_heartbeat_at"],
        unique=False,
    )


def _create_normalized_tables(existing_tables: set[str]) -> None:
    if "seller_onboarding_linux_host_probes" not in existing_tables:
        op.create_table(
            "seller_onboarding_linux_host_probes",
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("seller_user_id", sa.String(length=128), nullable=False),
            sa.Column("reported_phase", sa.String(length=32), nullable=True),
            sa.Column("host_name", sa.String(length=128), nullable=True),
            sa.Column("os_name", sa.String(length=128), nullable=True),
            sa.Column("distribution_name", sa.String(length=128), nullable=True),
            sa.Column("kernel_release", sa.String(length=128), nullable=True),
            sa.Column("virtualization_available", sa.Boolean(), nullable=True),
            sa.Column("sudo_available", sa.Boolean(), nullable=True),
            sa.Column("observed_ips", sa.JSON(), nullable=False),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_seller_onboarding_linux_host_probes_seller_user_id",
            "seller_onboarding_linux_host_probes",
            ["seller_user_id"],
            unique=False,
        )

    if "seller_onboarding_linux_substrate_probes" not in existing_tables:
        op.create_table(
            "seller_onboarding_linux_substrate_probes",
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("seller_user_id", sa.String(length=128), nullable=False),
            sa.Column("reported_phase", sa.String(length=32), nullable=True),
            sa.Column("distribution_name", sa.String(length=128), nullable=True),
            sa.Column("kernel_release", sa.String(length=128), nullable=True),
            sa.Column("docker_available", sa.Boolean(), nullable=True),
            sa.Column("docker_version", sa.String(length=128), nullable=True),
            sa.Column("wireguard_available", sa.Boolean(), nullable=True),
            sa.Column("gpu_available", sa.Boolean(), nullable=True),
            sa.Column("cpu_cores", sa.Integer(), nullable=True),
            sa.Column("memory_gb", sa.Integer(), nullable=True),
            sa.Column("disk_free_gb", sa.Integer(), nullable=True),
            sa.Column("observed_ips", sa.JSON(), nullable=False),
            sa.Column("observed_wireguard_ip", sa.String(length=64), nullable=True),
            sa.Column("observed_advertise_addr", sa.String(length=128), nullable=True),
            sa.Column("observed_data_path_addr", sa.String(length=128), nullable=True),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_seller_onboarding_linux_substrate_probes_seller_user_id",
            "seller_onboarding_linux_substrate_probes",
            ["seller_user_id"],
            unique=False,
        )

    if "seller_onboarding_container_runtime_probes" not in existing_tables:
        op.create_table(
            "seller_onboarding_container_runtime_probes",
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("seller_user_id", sa.String(length=128), nullable=False),
            sa.Column("reported_phase", sa.String(length=32), nullable=True),
            sa.Column("runtime_name", sa.String(length=128), nullable=True),
            sa.Column("runtime_version", sa.String(length=128), nullable=True),
            sa.Column("engine_available", sa.Boolean(), nullable=True),
            sa.Column("image_store_accessible", sa.Boolean(), nullable=True),
            sa.Column("network_ready", sa.Boolean(), nullable=True),
            sa.Column("observed_images", sa.JSON(), nullable=False),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_seller_onboarding_container_runtime_probes_seller_user_id",
            "seller_onboarding_container_runtime_probes",
            ["seller_user_id"],
            unique=False,
        )

    if "seller_onboarding_join_completions" not in existing_tables:
        op.create_table(
            "seller_onboarding_join_completions",
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("seller_user_id", sa.String(length=128), nullable=False),
            sa.Column("reported_phase", sa.String(length=32), nullable=True),
            sa.Column("node_ref", sa.String(length=128), nullable=True),
            sa.Column("compute_node_id", sa.String(length=128), nullable=True),
            sa.Column("observed_wireguard_ip", sa.String(length=64), nullable=True),
            sa.Column("observed_advertise_addr", sa.String(length=128), nullable=True),
            sa.Column("observed_data_path_addr", sa.String(length=128), nullable=True),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_seller_onboarding_join_completions_seller_user_id",
            "seller_onboarding_join_completions",
            ["seller_user_id"],
            unique=False,
        )

    if "seller_onboarding_corrections" not in existing_tables:
        op.create_table(
            "seller_onboarding_corrections",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), nullable=False),
            sa.Column("seller_user_id", sa.String(length=128), nullable=False),
            sa.Column("reported_phase", sa.String(length=32), nullable=True),
            sa.Column("source_surface", sa.String(length=64), nullable=True),
            sa.Column("correction_action", sa.String(length=128), nullable=False),
            sa.Column("target_wireguard_ip", sa.String(length=64), nullable=True),
            sa.Column("observed_advertise_addr", sa.String(length=128), nullable=True),
            sa.Column("observed_data_path_addr", sa.String(length=128), nullable=True),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_seller_onboarding_corrections_join_session_id", "seller_onboarding_corrections", ["join_session_id"], unique=False)
        op.create_index("ix_seller_onboarding_corrections_seller_user_id", "seller_onboarding_corrections", ["seller_user_id"], unique=False)

    if "seller_onboarding_manager_address_overrides" not in existing_tables:
        op.create_table(
            "seller_onboarding_manager_address_overrides",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("seller_user_id", sa.String(length=128), nullable=False),
            sa.Column("reported_phase", sa.String(length=32), nullable=True),
            sa.Column("source_surface", sa.String(length=64), nullable=True),
            sa.Column("override_target_addr", sa.String(length=128), nullable=False),
            sa.Column("override_reason", sa.String(length=256), nullable=False),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_so_mgr_addr_overrides_join_session_id",
            "seller_onboarding_manager_address_overrides",
            ["join_session_id"],
            unique=True,
        )
        op.create_index(
            "ix_so_mgr_addr_overrides_seller_user_id",
            "seller_onboarding_manager_address_overrides",
            ["seller_user_id"],
            unique=False,
        )

    if "seller_onboarding_authoritative_effective_targets" not in existing_tables:
        op.create_table(
            "seller_onboarding_authoritative_effective_targets",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("seller_user_id", sa.String(length=128), nullable=False),
            sa.Column("reported_phase", sa.String(length=32), nullable=True),
            sa.Column("source_surface", sa.String(length=64), nullable=True),
            sa.Column("effective_target_addr", sa.String(length=128), nullable=False),
            sa.Column("effective_target_reason", sa.String(length=256), nullable=False),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_so_auth_targets_join_session_id",
            "seller_onboarding_authoritative_effective_targets",
            ["join_session_id"],
            unique=True,
        )
        op.create_index(
            "ix_so_auth_targets_seller_user_id",
            "seller_onboarding_authoritative_effective_targets",
            ["seller_user_id"],
            unique=False,
        )

    if "seller_onboarding_manager_acceptances" not in existing_tables:
        op.create_table(
            "seller_onboarding_manager_acceptances",
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("expected_wireguard_ip", sa.String(length=64), nullable=True),
            sa.Column("observed_manager_node_addr", sa.String(length=128), nullable=True),
            sa.Column("matched", sa.Boolean(), nullable=True),
            sa.Column("node_ref", sa.String(length=128), nullable=True),
            sa.Column("compute_node_id", sa.String(length=128), nullable=True),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("detail", sa.String(length=255), nullable=True),
        )
        op.create_index(
            "ix_seller_onboarding_manager_acceptances_status",
            "seller_onboarding_manager_acceptances",
            ["status"],
            unique=False,
        )

    if "seller_onboarding_manager_acceptance_history" not in existing_tables:
        op.create_table(
            "seller_onboarding_manager_acceptance_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("expected_wireguard_ip", sa.String(length=64), nullable=True),
            sa.Column("observed_manager_node_addr", sa.String(length=128), nullable=True),
            sa.Column("matched", sa.Boolean(), nullable=True),
            sa.Column("node_ref", sa.String(length=128), nullable=True),
            sa.Column("compute_node_id", sa.String(length=128), nullable=True),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("detail", sa.String(length=255), nullable=True),
        )
        op.create_index(
            "ix_so_mgr_accept_hist_join_session_id",
            "seller_onboarding_manager_acceptance_history",
            ["join_session_id"],
            unique=False,
        )
        op.create_index(
            "ix_so_mgr_accept_hist_status",
            "seller_onboarding_manager_acceptance_history",
            ["status"],
            unique=False,
        )

    if "seller_onboarding_minimum_tcp_validations" not in existing_tables:
        op.create_table(
            "seller_onboarding_minimum_tcp_validations",
            sa.Column("join_session_id", sa.String(length=64), sa.ForeignKey(f"{SESSION_TABLE}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("seller_user_id", sa.String(length=128), nullable=False),
            sa.Column("reported_phase", sa.String(length=32), nullable=True),
            sa.Column("target_addr", sa.String(length=128), nullable=True),
            sa.Column("target_port", sa.Integer(), nullable=False),
            sa.Column("protocol", sa.String(length=16), nullable=False),
            sa.Column("reachable", sa.Boolean(), nullable=False),
            sa.Column("validated_against_manager_target", sa.Boolean(), nullable=False),
            sa.Column("validated_against_effective_target", sa.Boolean(), nullable=False),
            sa.Column("effective_target_addr", sa.String(length=128), nullable=True),
            sa.Column("effective_target_source", sa.String(length=64), nullable=True),
            sa.Column("truth_authority", sa.String(length=64), nullable=False),
            sa.Column("detail", sa.String(length=255), nullable=True),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_seller_onboarding_minimum_tcp_validations_seller_user_id",
            "seller_onboarding_minimum_tcp_validations",
            ["seller_user_id"],
            unique=False,
        )


def _migrate_legacy_json_payloads(bind, legacy_columns: set[str]) -> None:
    metadata = sa.MetaData()
    session_table = sa.Table(SESSION_TABLE, metadata, autoload_with=bind)
    host_table = sa.Table("seller_onboarding_linux_host_probes", metadata, autoload_with=bind)
    substrate_table = sa.Table("seller_onboarding_linux_substrate_probes", metadata, autoload_with=bind)
    runtime_table = sa.Table("seller_onboarding_container_runtime_probes", metadata, autoload_with=bind)
    join_complete_table = sa.Table("seller_onboarding_join_completions", metadata, autoload_with=bind)
    corrections_table = sa.Table("seller_onboarding_corrections", metadata, autoload_with=bind)
    override_table = sa.Table("seller_onboarding_manager_address_overrides", metadata, autoload_with=bind)
    authoritative_table = sa.Table("seller_onboarding_authoritative_effective_targets", metadata, autoload_with=bind)
    acceptance_table = sa.Table("seller_onboarding_manager_acceptances", metadata, autoload_with=bind)
    acceptance_history_table = sa.Table("seller_onboarding_manager_acceptance_history", metadata, autoload_with=bind)
    tcp_table = sa.Table("seller_onboarding_minimum_tcp_validations", metadata, autoload_with=bind)

    rows = bind.execute(sa.select(session_table)).mappings().all()
    for row in rows:
        session_id = row["id"]
        seller_user_id = row["seller_user_id"]

        if "linux_host_probe" in legacy_columns and row["linux_host_probe"]:
            payload = dict(row["linux_host_probe"])
            bind.execute(
                host_table.insert().values(
                    join_session_id=session_id,
                    seller_user_id=payload.get("seller_user_id") or seller_user_id,
                    reported_phase=payload.get("reported_phase"),
                    host_name=payload.get("host_name"),
                    os_name=payload.get("os_name"),
                    distribution_name=payload.get("distribution_name"),
                    kernel_release=payload.get("kernel_release"),
                    virtualization_available=payload.get("virtualization_available"),
                    sudo_available=payload.get("sudo_available"),
                    observed_ips=list(payload.get("observed_ips") or []),
                    notes=list(payload.get("notes") or []),
                    raw_payload=dict(payload.get("raw_payload") or {}),
                    recorded_at=_parse_datetime(payload.get("recorded_at")),
                )
            )

        if "linux_substrate_probe" in legacy_columns and row["linux_substrate_probe"]:
            payload = dict(row["linux_substrate_probe"])
            bind.execute(
                substrate_table.insert().values(
                    join_session_id=session_id,
                    seller_user_id=payload.get("seller_user_id") or seller_user_id,
                    reported_phase=payload.get("reported_phase"),
                    distribution_name=payload.get("distribution_name"),
                    kernel_release=payload.get("kernel_release"),
                    docker_available=payload.get("docker_available"),
                    docker_version=payload.get("docker_version"),
                    wireguard_available=payload.get("wireguard_available"),
                    gpu_available=payload.get("gpu_available"),
                    cpu_cores=payload.get("cpu_cores"),
                    memory_gb=payload.get("memory_gb"),
                    disk_free_gb=payload.get("disk_free_gb"),
                    observed_ips=list(payload.get("observed_ips") or []),
                    observed_wireguard_ip=payload.get("observed_wireguard_ip"),
                    observed_advertise_addr=payload.get("observed_advertise_addr"),
                    observed_data_path_addr=payload.get("observed_data_path_addr"),
                    notes=list(payload.get("notes") or []),
                    raw_payload=dict(payload.get("raw_payload") or {}),
                    recorded_at=_parse_datetime(payload.get("recorded_at")),
                )
            )

        if "container_runtime_probe" in legacy_columns and row["container_runtime_probe"]:
            payload = dict(row["container_runtime_probe"])
            bind.execute(
                runtime_table.insert().values(
                    join_session_id=session_id,
                    seller_user_id=payload.get("seller_user_id") or seller_user_id,
                    reported_phase=payload.get("reported_phase"),
                    runtime_name=payload.get("runtime_name"),
                    runtime_version=payload.get("runtime_version"),
                    engine_available=payload.get("engine_available"),
                    image_store_accessible=payload.get("image_store_accessible"),
                    network_ready=payload.get("network_ready"),
                    observed_images=list(payload.get("observed_images") or []),
                    notes=list(payload.get("notes") or []),
                    raw_payload=dict(payload.get("raw_payload") or {}),
                    recorded_at=_parse_datetime(payload.get("recorded_at")),
                )
            )

        if "join_complete" in legacy_columns and row["join_complete"]:
            payload = dict(row["join_complete"])
            bind.execute(
                join_complete_table.insert().values(
                    join_session_id=session_id,
                    seller_user_id=payload.get("seller_user_id") or seller_user_id,
                    reported_phase=payload.get("reported_phase"),
                    node_ref=payload.get("node_ref"),
                    compute_node_id=payload.get("compute_node_id"),
                    observed_wireguard_ip=payload.get("observed_wireguard_ip"),
                    observed_advertise_addr=payload.get("observed_advertise_addr"),
                    observed_data_path_addr=payload.get("observed_data_path_addr"),
                    notes=list(payload.get("notes") or []),
                    raw_payload=dict(payload.get("raw_payload") or {}),
                    submitted_at=_parse_datetime(payload.get("submitted_at")),
                )
            )

        if "corrections" in legacy_columns and row["corrections"]:
            for payload in list(row["corrections"] or []):
                item = dict(payload)
                bind.execute(
                    corrections_table.insert().values(
                        id=item.get("id"),
                        join_session_id=session_id,
                        seller_user_id=item.get("seller_user_id") or seller_user_id,
                        reported_phase=item.get("reported_phase"),
                        source_surface=item.get("source_surface"),
                        correction_action=item.get("correction_action"),
                        target_wireguard_ip=item.get("target_wireguard_ip"),
                        observed_advertise_addr=item.get("observed_advertise_addr"),
                        observed_data_path_addr=item.get("observed_data_path_addr"),
                        notes=list(item.get("notes") or []),
                        raw_payload=dict(item.get("raw_payload") or {}),
                        recorded_at=_parse_datetime(item.get("recorded_at")),
                    )
                )

        if "manager_address_override" in legacy_columns and row["manager_address_override"]:
            payload = dict(row["manager_address_override"])
            bind.execute(
                override_table.insert().values(
                    id=payload.get("id"),
                    join_session_id=session_id,
                    seller_user_id=payload.get("seller_user_id") or seller_user_id,
                    reported_phase=payload.get("reported_phase"),
                    source_surface=payload.get("source_surface"),
                    override_target_addr=payload.get("override_target_addr"),
                    override_reason=payload.get("override_reason"),
                    notes=list(payload.get("notes") or []),
                    raw_payload=dict(payload.get("raw_payload") or {}),
                    recorded_at=_parse_datetime(payload.get("recorded_at")),
                )
            )

        if "authoritative_effective_target" in legacy_columns and row["authoritative_effective_target"]:
            payload = dict(row["authoritative_effective_target"])
            bind.execute(
                authoritative_table.insert().values(
                    id=payload.get("id"),
                    join_session_id=session_id,
                    seller_user_id=payload.get("seller_user_id") or seller_user_id,
                    reported_phase=payload.get("reported_phase"),
                    source_surface=payload.get("source_surface"),
                    effective_target_addr=payload.get("effective_target_addr"),
                    effective_target_reason=payload.get("effective_target_reason"),
                    notes=list(payload.get("notes") or []),
                    raw_payload=dict(payload.get("raw_payload") or {}),
                    recorded_at=_parse_datetime(payload.get("recorded_at")),
                )
            )

        if "manager_acceptance" in legacy_columns and row["manager_acceptance"]:
            payload = dict(row["manager_acceptance"])
            bind.execute(
                acceptance_table.insert().values(
                    join_session_id=session_id,
                    status=payload.get("status"),
                    expected_wireguard_ip=payload.get("expected_wireguard_ip"),
                    observed_manager_node_addr=payload.get("observed_manager_node_addr"),
                    matched=payload.get("matched"),
                    node_ref=payload.get("node_ref"),
                    compute_node_id=payload.get("compute_node_id"),
                    checked_at=_parse_datetime(payload.get("checked_at")),
                    detail=payload.get("detail"),
                )
            )

        if "manager_acceptance_history" in legacy_columns and row["manager_acceptance_history"]:
            for payload in list(row["manager_acceptance_history"] or []):
                item = dict(payload)
                bind.execute(
                    acceptance_history_table.insert().values(
                        join_session_id=session_id,
                        status=item.get("status"),
                        expected_wireguard_ip=item.get("expected_wireguard_ip"),
                        observed_manager_node_addr=item.get("observed_manager_node_addr"),
                        matched=item.get("matched"),
                        node_ref=item.get("node_ref"),
                        compute_node_id=item.get("compute_node_id"),
                        checked_at=_parse_datetime(item.get("checked_at")),
                        detail=item.get("detail"),
                    )
                )

        if "minimum_tcp_validation" in legacy_columns and row["minimum_tcp_validation"]:
            payload = dict(row["minimum_tcp_validation"])
            bind.execute(
                tcp_table.insert().values(
                    join_session_id=session_id,
                    seller_user_id=payload.get("seller_user_id") or seller_user_id,
                    reported_phase=payload.get("reported_phase"),
                    target_addr=payload.get("target_addr"),
                    target_port=payload.get("target_port"),
                    protocol=payload.get("protocol"),
                    reachable=payload.get("reachable"),
                    validated_against_manager_target=payload.get("validated_against_manager_target"),
                    validated_against_effective_target=payload.get("validated_against_effective_target"),
                    effective_target_addr=payload.get("effective_target_addr"),
                    effective_target_source=payload.get("effective_target_source"),
                    truth_authority=payload.get("truth_authority"),
                    detail=payload.get("detail"),
                    notes=list(payload.get("notes") or []),
                    raw_payload=dict(payload.get("raw_payload") or {}),
                    checked_at=_parse_datetime(payload.get("checked_at")),
                )
            )


def _rebuild_legacy_json_payloads(bind) -> None:
    metadata = sa.MetaData()
    session_table = sa.Table(SESSION_TABLE, metadata, autoload_with=bind)
    host_table = sa.Table("seller_onboarding_linux_host_probes", metadata, autoload_with=bind)
    substrate_table = sa.Table("seller_onboarding_linux_substrate_probes", metadata, autoload_with=bind)
    runtime_table = sa.Table("seller_onboarding_container_runtime_probes", metadata, autoload_with=bind)
    join_complete_table = sa.Table("seller_onboarding_join_completions", metadata, autoload_with=bind)
    corrections_table = sa.Table("seller_onboarding_corrections", metadata, autoload_with=bind)
    override_table = sa.Table("seller_onboarding_manager_address_overrides", metadata, autoload_with=bind)
    authoritative_table = sa.Table("seller_onboarding_authoritative_effective_targets", metadata, autoload_with=bind)
    acceptance_table = sa.Table("seller_onboarding_manager_acceptances", metadata, autoload_with=bind)
    acceptance_history_table = sa.Table("seller_onboarding_manager_acceptance_history", metadata, autoload_with=bind)
    tcp_table = sa.Table("seller_onboarding_minimum_tcp_validations", metadata, autoload_with=bind)

    session_rows = bind.execute(sa.select(session_table)).mappings().all()
    for row in session_rows:
        session_id = row["id"]
        bind.execute(
            session_table.update()
            .where(session_table.c.id == session_id)
            .values(
                linux_host_probe=_row_mapping_or_none(bind.execute(sa.select(host_table).where(host_table.c.join_session_id == session_id)).mappings().first()),
                linux_substrate_probe=_row_mapping_or_none(bind.execute(sa.select(substrate_table).where(substrate_table.c.join_session_id == session_id)).mappings().first()),
                container_runtime_probe=_row_mapping_or_none(bind.execute(sa.select(runtime_table).where(runtime_table.c.join_session_id == session_id)).mappings().first()),
                join_complete=_row_mapping_or_none(bind.execute(sa.select(join_complete_table).where(join_complete_table.c.join_session_id == session_id)).mappings().first()),
                corrections=[dict(item) for item in bind.execute(sa.select(corrections_table).where(corrections_table.c.join_session_id == session_id)).mappings().all()],
                manager_address_override=_row_mapping_or_none(bind.execute(sa.select(override_table).where(override_table.c.join_session_id == session_id)).mappings().first()),
                authoritative_effective_target=_row_mapping_or_none(bind.execute(sa.select(authoritative_table).where(authoritative_table.c.join_session_id == session_id)).mappings().first()),
                manager_acceptance=_row_mapping_or_none(bind.execute(sa.select(acceptance_table).where(acceptance_table.c.join_session_id == session_id)).mappings().first()),
                manager_acceptance_history=[dict(item) for item in bind.execute(sa.select(acceptance_history_table).where(acceptance_history_table.c.join_session_id == session_id)).mappings().all()],
                minimum_tcp_validation=_row_mapping_or_none(bind.execute(sa.select(tcp_table).where(tcp_table.c.join_session_id == session_id)).mappings().first()),
            )
        )


def _row_mapping_or_none(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    payload.pop("join_session_id", None)
    return {key: _json_ready(value) for key, value in payload.items()}


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return value


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
