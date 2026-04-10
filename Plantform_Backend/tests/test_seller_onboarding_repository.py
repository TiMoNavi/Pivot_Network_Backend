from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend_app.db.base import Base
from backend_app.db import models  # noqa: F401
from backend_app.repositories.seller_onboarding_repository import SellerOnboardingRepository
from backend_app.storage.memory_store import JoinSessionRecord, LinuxHostProbeRecord, ManagerAcceptanceRecord


def test_repository_persists_onboarding_state_in_normalized_tables(tmp_path) -> None:
    db_path = tmp_path / "seller_onboarding_repository.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime.now(UTC)
    with session_local() as db:
        repository = SellerOnboardingRepository(db)
        session = JoinSessionRecord(
            id="join_session_repo_1",
            seller_user_id="seller-user-1",
            status="issued",
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
            expires_at=now + timedelta(hours=1),
            last_heartbeat_at=now,
            created_at=now,
            updated_at=now,
        )
        repository.save_session(session)
        repository.save_linux_host_probe(
            LinuxHostProbeRecord(
                join_session_id=session.id,
                seller_user_id=session.seller_user_id,
                reported_phase="detect",
                host_name="seller-host-1",
                os_name="linux",
                distribution_name="ubuntu",
                kernel_release="6.8.0",
                virtualization_available=True,
                sudo_available=True,
                observed_ips=["192.168.1.10"],
                notes=["host-ready"],
                raw_payload={"source": "unit-test"},
                recorded_at=now,
            )
        )
        repository.set_manager_acceptance(
            session.id,
            ManagerAcceptanceRecord(
                status="pending",
                expected_wireguard_ip="10.66.66.10",
                observed_manager_node_addr=None,
                matched=None,
                node_ref=None,
                compute_node_id="compute-node-1",
                checked_at=None,
                detail="awaiting_join_complete",
            ),
            append_history=True,
        )
        repository.commit()

    with session_local() as db:
        repository = SellerOnboardingRepository(db)
        persisted_session = repository.get_session("join_session_repo_1")
        persisted_host_probe = repository.get_linux_host_probe("join_session_repo_1")
        persisted_acceptance = repository.get_manager_acceptance("join_session_repo_1")
        acceptance_history = repository.list_manager_acceptance_history("join_session_repo_1")

    assert persisted_session is not None
    assert persisted_session.expected_wireguard_ip == "10.66.66.10"
    assert persisted_host_probe is not None
    assert persisted_host_probe.host_name == "seller-host-1"
    assert persisted_acceptance is not None
    assert persisted_acceptance.detail == "awaiting_join_complete"
    assert len(acceptance_history) == 1

    inspector = inspect(engine)
    session_columns = {column["name"] for column in inspector.get_columns("seller_onboarding_sessions")}
    assert "linux_host_probe" not in session_columns
    assert "manager_acceptance" not in session_columns
    assert "minimum_tcp_validation" not in session_columns

    tables = set(inspector.get_table_names())
    assert "seller_onboarding_linux_host_probes" in tables
    assert "seller_onboarding_manager_acceptances" in tables
    assert "seller_onboarding_manager_acceptance_history" in tables
