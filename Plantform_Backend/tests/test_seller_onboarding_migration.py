from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, Boolean, Column, DateTime, MetaData, String, Table, create_engine, inspect, insert, select

from backend_app.core.config import get_settings


def test_alembic_upgrade_migrates_legacy_json_onboarding_table(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "legacy_onboarding.db"
    db_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    metadata = MetaData()
    legacy_table = Table(
        "seller_onboarding_sessions",
        metadata,
        Column("id", String(64), primary_key=True),
        Column("seller_user_id", String(128), nullable=False),
        Column("status", String(32), nullable=False),
        Column("one_time_token", String(255), nullable=False),
        Column("requested_offer_tier", String(32), nullable=True),
        Column("requested_accelerator", String(32), nullable=False),
        Column("requested_compute_node_id", String(128), nullable=True),
        Column("swarm_join_material", JSON, nullable=False),
        Column("required_labels", JSON, nullable=False),
        Column("expected_wireguard_ip", String(64), nullable=True),
        Column("linux_host_probe", JSON, nullable=True),
        Column("linux_substrate_probe", JSON, nullable=True),
        Column("container_runtime_probe", JSON, nullable=True),
        Column("join_complete", JSON, nullable=True),
        Column("corrections", JSON, nullable=True),
        Column("manager_address_override", JSON, nullable=True),
        Column("authoritative_effective_target", JSON, nullable=True),
        Column("manager_acceptance", JSON, nullable=True),
        Column("manager_acceptance_history", JSON, nullable=True),
        Column("minimum_tcp_validation", JSON, nullable=True),
        Column("expires_at", DateTime(timezone=True), nullable=False),
        Column("last_heartbeat_at", DateTime(timezone=True), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(bind=engine)

    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(legacy_table).values(
                id="join_session_legacy_1",
                seller_user_id="seller-user-1",
                status="verified",
                one_time_token="token-1",
                requested_offer_tier="medium",
                requested_accelerator="gpu",
                requested_compute_node_id="compute-node-1",
                swarm_join_material={
                    "manager_addr": "10.66.66.1",
                    "manager_port": 2377,
                    "swarm_join_command": "docker swarm join --token join-token 10.66.66.1:2377",
                },
                required_labels={"platform.compute_node_id": "compute-node-1"},
                expected_wireguard_ip="10.66.66.10",
                linux_host_probe={
                    "join_session_id": "join_session_legacy_1",
                    "seller_user_id": "seller-user-1",
                    "reported_phase": "detect",
                    "host_name": "seller-host-legacy",
                    "os_name": "linux",
                    "distribution_name": "ubuntu",
                    "kernel_release": "6.8.0",
                    "virtualization_available": True,
                    "sudo_available": True,
                    "observed_ips": ["192.168.1.10"],
                    "notes": ["legacy-host"],
                    "raw_payload": {"source": "legacy"},
                    "recorded_at": now.isoformat(),
                },
                manager_acceptance={
                    "status": "matched",
                    "expected_wireguard_ip": "10.66.66.10",
                    "observed_manager_node_addr": "10.66.66.10",
                    "matched": True,
                    "node_ref": "node-1",
                    "compute_node_id": "compute-node-1",
                    "checked_at": now.isoformat(),
                    "detail": None,
                },
                manager_acceptance_history=[
                    {
                        "status": "matched",
                        "expected_wireguard_ip": "10.66.66.10",
                        "observed_manager_node_addr": "10.66.66.10",
                        "matched": True,
                        "node_ref": "node-1",
                        "compute_node_id": "compute-node-1",
                        "checked_at": now.isoformat(),
                        "detail": None,
                    }
                ],
                minimum_tcp_validation={
                    "join_session_id": "join_session_legacy_1",
                    "seller_user_id": "seller-user-1",
                    "reported_phase": "repair",
                    "target_addr": "10.66.66.10",
                    "target_port": 8080,
                    "protocol": "tcp",
                    "reachable": True,
                    "validated_against_manager_target": True,
                    "validated_against_effective_target": True,
                    "effective_target_addr": "10.66.66.10",
                    "effective_target_source": "manager_matched",
                    "truth_authority": "raw_manager",
                    "detail": None,
                    "notes": ["legacy-tcp"],
                    "raw_payload": {"source": "legacy"},
                    "checked_at": now.isoformat(),
                },
                corrections=[
                    {
                        "id": "correction_1",
                        "join_session_id": "join_session_legacy_1",
                        "seller_user_id": "seller-user-1",
                        "reported_phase": "repair",
                        "source_surface": "docker_swarm",
                        "correction_action": "set_explicit_advertise_and_data_path_addr",
                        "target_wireguard_ip": "10.66.66.10",
                        "observed_advertise_addr": "10.66.66.10",
                        "observed_data_path_addr": "10.66.66.10",
                        "notes": ["legacy-correction"],
                        "raw_payload": {"source": "legacy"},
                        "recorded_at": now.isoformat(),
                    }
                ],
                expires_at=now + timedelta(hours=1),
                last_heartbeat_at=now,
                created_at=now,
                updated_at=now,
            )
        )

    monkeypatch.setenv("BACKEND_POSTGRES_URL", db_url)
    get_settings.cache_clear()
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    command.upgrade(config, "head")
    get_settings.cache_clear()

    inspector = inspect(engine)
    session_columns = {column["name"] for column in inspector.get_columns("seller_onboarding_sessions")}
    assert "linux_host_probe" not in session_columns
    assert "manager_acceptance" not in session_columns
    assert "minimum_tcp_validation" not in session_columns
    assert "seller_onboarding_linux_host_probes" in inspector.get_table_names()
    assert "users" in inspector.get_table_names()
    assert "offers" in inspector.get_table_names()
    assert "seller_capability_assessments" in inspector.get_table_names()

    metadata_after = MetaData()
    host_table = Table("seller_onboarding_linux_host_probes", metadata_after, autoload_with=engine)
    acceptance_table = Table("seller_onboarding_manager_acceptances", metadata_after, autoload_with=engine)
    acceptance_history_table = Table("seller_onboarding_manager_acceptance_history", metadata_after, autoload_with=engine)
    tcp_table = Table("seller_onboarding_minimum_tcp_validations", metadata_after, autoload_with=engine)
    corrections_table = Table("seller_onboarding_corrections", metadata_after, autoload_with=engine)
    offers_table = Table("offers", metadata_after, autoload_with=engine)
    assessment_table = Table("seller_capability_assessments", metadata_after, autoload_with=engine)

    with engine.connect() as connection:
        host_row = connection.execute(select(host_table)).mappings().one()
        acceptance_row = connection.execute(select(acceptance_table)).mappings().one()
        acceptance_history_rows = connection.execute(select(acceptance_history_table)).mappings().all()
        tcp_row = connection.execute(select(tcp_table)).mappings().one()
        correction_row = connection.execute(select(corrections_table)).mappings().one()
        seeded_offers = connection.execute(select(offers_table)).mappings().all()
        assessments = connection.execute(select(assessment_table)).mappings().all()

    assert host_row["host_name"] == "seller-host-legacy"
    assert acceptance_row["status"] == "matched"
    assert len(acceptance_history_rows) == 1
    assert tcp_row["target_port"] == 8080
    assert correction_row["correction_action"] == "set_explicit_advertise_and_data_path_addr"
    assert "compute_node_id" in offers_table.c
    assert "source_join_session_id" in offers_table.c
    assert "source_assessment_id" in offers_table.c
    assert assessments == []
    assert seeded_offers == []
