from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend_app.api.deps import get_auth_service, get_file_service, get_trade_service
from backend_app.db.base import Base
from backend_app.main import app
from backend_app.repositories.seller_onboarding_repository import SellerOnboardingRepository
from backend_app.services.auth_service import AuthService
from backend_app.services.file_service import FileService
from backend_app.services.trade_service import TradeService
from backend_app.storage.memory_store import (
    AuthoritativeEffectiveTargetRecord,
    InMemoryStore,
    JoinSessionRecord,
    ManagerAcceptanceRecord,
    ManagerAddressOverrideRecord,
    MinimumTcpValidationRecord,
)


def test_auth_offer_order_and_access_grant_flow(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    store = InMemoryStore()
    store.seed_offers()
    auth_service = AuthService(store)
    trade_service = TradeService(store, download_root=downloads)
    file_service = FileService(downloads)

    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_trade_service] = lambda: trade_service
    app.dependency_overrides[get_file_service] = lambda: file_service

    client = TestClient(app)

    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "buyer@example.com",
            "display_name": "Buyer One",
            "password": "password123",
            "role": "buyer",
        },
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "buyer@example.com"

    offers = client.get("/api/v1/offers")
    assert offers.status_code == 200, offers.text
    offers_payload = offers.json()
    assert offers_payload["total"] >= 1
    offer_id = offers_payload["items"][0]["id"]

    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "offer_id": offer_id,
            "requested_duration_minutes": 60,
        },
    )
    assert order.status_code == 201, order.text
    order_payload = order.json()
    assert order_payload["offer_id"] == offer_id
    order_id = order_payload["id"]

    activation = client.post(f"/api/v1/orders/{order_id}/activate", headers=headers)
    assert activation.status_code == 200, activation.text
    activation_payload = activation.json()
    grant = activation_payload["access_grant"]
    assert grant["status"] == "issued"
    download_relative_path = grant["connect_material_payload"]["download_relative_path"]

    grants = client.get("/api/v1/me/access-grants/active", headers=headers)
    assert grants.status_code == 200, grants.text
    assert grants.json()["total"] == 1

    listing = client.get("/api/v1/files/")
    assert listing.status_code == 200, listing.text
    assert any(item["relative_path"] == download_relative_path for item in listing.json()["items"])

    download = client.get(f"/api/v1/files/download/{download_relative_path}")
    assert download.status_code == 200, download.text
    assert "placeholder-runtime" in download.text

    app.dependency_overrides.clear()


def test_access_grant_exposes_effective_target_from_override_lane(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    store = InMemoryStore()
    store.seed_offers()
    auth_service = AuthService(store)
    trade_service = TradeService(store, download_root=downloads)
    file_service = FileService(downloads)

    now = datetime.now(UTC)
    session = JoinSessionRecord(
        id="join_session_effective_target",
        seller_user_id="seed-seller-1",
        status="verify_failed",
        one_time_token="token-1",
        requested_offer_tier="medium",
        requested_accelerator="gpu",
        requested_compute_node_id="seed-node-1",
        swarm_join_material={
            "join_token": "join-token",
            "manager_addr": "10.66.66.1",
            "manager_port": 2377,
            "registry_host": "pivotcompute.store",
            "registry_port": 5000,
            "swarm_join_command": "docker swarm join --token join-token 10.66.66.1:2377",
            "claim_required": True,
            "recommended_compute_node_id": "seed-node-1",
            "expected_wireguard_ip": "10.66.66.10",
            "recommended_labels": {},
            "next_step": "seller_host_runs_join_then_backend_calls_claim",
        },
        required_labels={},
        expected_wireguard_ip="10.66.66.10",
        expires_at=now + timedelta(hours=1),
        last_heartbeat_at=now,
        created_at=now,
        updated_at=now,
    )
    store.join_sessions[session.id] = session
    store.manager_acceptance_by_session_id[session.id] = ManagerAcceptanceRecord(
        status="mismatch",
        expected_wireguard_ip="10.66.66.10",
        observed_manager_node_addr="202.113.184.2",
        matched=False,
        node_ref="node-1",
        compute_node_id="seed-node-1",
        checked_at=now,
        detail="manager_node_addr_mismatch",
    )
    store.manager_address_override_by_session_id[session.id] = ManagerAddressOverrideRecord(
        id="manager_override_1",
        join_session_id=session.id,
        seller_user_id=session.seller_user_id,
        reported_phase="repair",
        source_surface="operator_override",
        override_target_addr="10.66.66.10",
        override_reason="formal workflow override lane",
        notes=["force-route for buyer workflow"],
        raw_payload={},
        recorded_at=now,
    )

    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_trade_service] = lambda: trade_service
    app.dependency_overrides[get_file_service] = lambda: file_service

    client = TestClient(app)

    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "buyer-override@example.com",
            "display_name": "Buyer Override",
            "password": "password123",
            "role": "buyer",
        },
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "offer_id": "offer-medium-gpu",
            "requested_duration_minutes": 60,
        },
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]

    activation = client.post(f"/api/v1/orders/{order_id}/activate", headers=headers)
    assert activation.status_code == 200, activation.text
    payload = activation.json()["access_grant"]["connect_material_payload"]
    assert payload["grant_mode"] == "effective_target_available"
    assert payload["network_mode"] == "effective_target"
    assert payload["join_session_id"] == "join_session_effective_target"
    assert payload["effective_target_addr"] == "10.66.66.10"
    assert payload["effective_target_source"] == "operator_override"
    assert payload["raw_manager_acceptance_status"] == "mismatch"
    assert payload["raw_manager_node_addr"] == "202.113.184.2"
    assert payload["truth_authority"] == "backend_correction"
    assert payload["minimum_tcp_validation"] is None

    app.dependency_overrides.clear()


def test_access_grant_exposes_authoritative_target_and_tcp_validation_snapshot(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    store = InMemoryStore()
    store.seed_offers()
    auth_service = AuthService(store)
    trade_service = TradeService(store, download_root=downloads)
    file_service = FileService(downloads)

    now = datetime.now(UTC)
    session = JoinSessionRecord(
        id="join_session_authoritative_target",
        seller_user_id="seed-seller-1",
        status="verified",
        one_time_token="token-1",
        requested_offer_tier="medium",
        requested_accelerator="gpu",
        requested_compute_node_id="seed-node-1",
        swarm_join_material={
            "join_token": "join-token",
            "manager_addr": "10.66.66.1",
            "manager_port": 2377,
            "registry_host": "pivotcompute.store",
            "registry_port": 5000,
            "swarm_join_command": "docker swarm join --token join-token 10.66.66.1:2377",
            "claim_required": True,
            "recommended_compute_node_id": "seed-node-1",
            "expected_wireguard_ip": "10.66.66.10",
            "recommended_labels": {},
            "next_step": "seller_host_runs_join_then_backend_calls_claim",
        },
        required_labels={},
        expected_wireguard_ip="10.66.66.10",
        expires_at=now + timedelta(hours=1),
        last_heartbeat_at=now,
        created_at=now,
        updated_at=now,
    )
    store.join_sessions[session.id] = session
    store.manager_acceptance_by_session_id[session.id] = ManagerAcceptanceRecord(
        status="mismatch",
        expected_wireguard_ip="10.66.66.10",
        observed_manager_node_addr="202.113.184.2",
        matched=False,
        node_ref="node-1",
        compute_node_id="seed-node-1",
        checked_at=now,
        detail="manager_node_addr_mismatch",
    )
    store.authoritative_effective_target_by_session_id[session.id] = AuthoritativeEffectiveTargetRecord(
        id="authoritative_target_1",
        join_session_id=session.id,
        seller_user_id=session.seller_user_id,
        reported_phase="repair",
        source_surface="backend_authoritative_workflow",
        effective_target_addr="10.66.66.10",
        effective_target_reason="fresh runtime evidence plus raw manager mismatch",
        notes=["formal backend correction"],
        raw_payload={},
        recorded_at=now,
    )
    store.minimum_tcp_validation_by_session_id[session.id] = MinimumTcpValidationRecord(
        join_session_id=session.id,
        seller_user_id=session.seller_user_id,
        reported_phase="repair",
        target_addr="10.66.66.10",
        target_port=8080,
        protocol="tcp",
        reachable=True,
        validated_against_manager_target=False,
        validated_against_effective_target=True,
        effective_target_addr="10.66.66.10",
        effective_target_source="backend_correction",
        truth_authority="backend_correction",
        detail=None,
        notes=["backend-authoritative tcp validation"],
        raw_payload={},
        checked_at=now,
    )

    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_trade_service] = lambda: trade_service
    app.dependency_overrides[get_file_service] = lambda: file_service

    client = TestClient(app)

    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "buyer-authoritative@example.com",
            "display_name": "Buyer Authoritative",
            "password": "password123",
            "role": "buyer",
        },
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "offer_id": "offer-medium-gpu",
            "requested_duration_minutes": 60,
        },
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]

    activation = client.post(f"/api/v1/orders/{order_id}/activate", headers=headers)
    assert activation.status_code == 200, activation.text
    payload = activation.json()["access_grant"]["connect_material_payload"]
    assert payload["grant_mode"] == "effective_target_available"
    assert payload["network_mode"] == "effective_target"
    assert payload["join_session_id"] == "join_session_authoritative_target"
    assert payload["effective_target_addr"] == "10.66.66.10"
    assert payload["effective_target_source"] == "backend_correction"
    assert payload["truth_authority"] == "backend_correction"
    assert payload["minimum_tcp_validation"]["reachable"] is True
    assert payload["minimum_tcp_validation"]["validated_against_effective_target"] is True

    app.dependency_overrides.clear()


def test_access_grant_can_read_effective_target_from_database_backed_onboarding(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    store = InMemoryStore()
    store.seed_offers()
    auth_service = AuthService(store)

    db_dir = Path(tempfile.mkdtemp(prefix="trade-onboarding-db-"))
    engine = create_engine(
        f"sqlite+pysqlite:///{db_dir / 'onboarding.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db_session = session_local()
    repository = SellerOnboardingRepository(db_session)

    now = datetime.now(UTC)
    session = JoinSessionRecord(
        id="join_session_db_target",
        seller_user_id="seed-seller-1",
        status="verified",
        one_time_token="token-1",
        requested_offer_tier="medium",
        requested_accelerator="gpu",
        requested_compute_node_id="seed-node-1",
        swarm_join_material={
            "join_token": "join-token",
            "manager_addr": "10.66.66.1",
            "manager_port": 2377,
            "registry_host": "pivotcompute.store",
            "registry_port": 5000,
            "swarm_join_command": "docker swarm join --token join-token 10.66.66.1:2377",
            "claim_required": True,
            "recommended_compute_node_id": "seed-node-1",
            "expected_wireguard_ip": "10.66.66.10",
            "recommended_labels": {},
            "next_step": "seller_host_runs_join_then_backend_calls_claim",
        },
        required_labels={},
        expected_wireguard_ip="10.66.66.10",
        expires_at=now + timedelta(hours=1),
        last_heartbeat_at=now,
        created_at=now,
        updated_at=now,
    )
    repository.save_session(session)
    repository.set_manager_acceptance(
        session.id,
        ManagerAcceptanceRecord(
            status="mismatch",
            expected_wireguard_ip="10.66.66.10",
            observed_manager_node_addr="202.113.184.2",
            matched=False,
            node_ref="node-1",
            compute_node_id="seed-node-1",
            checked_at=now,
            detail="manager_node_addr_mismatch",
        ),
        append_history=True,
    )
    repository.save_authoritative_effective_target(
        AuthoritativeEffectiveTargetRecord(
            id="authoritative_target_db_1",
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase="repair",
            source_surface="backend_authoritative_workflow",
            effective_target_addr="10.66.66.10",
            effective_target_reason="database-backed correction",
            notes=["db-backed formal correction"],
            raw_payload={},
            recorded_at=now,
        )
    )
    repository.save_minimum_tcp_validation(
        MinimumTcpValidationRecord(
            join_session_id=session.id,
            seller_user_id=session.seller_user_id,
            reported_phase="repair",
            target_addr="10.66.66.10",
            target_port=8080,
            protocol="tcp",
            reachable=True,
            validated_against_manager_target=False,
            validated_against_effective_target=True,
            effective_target_addr="10.66.66.10",
            effective_target_source="backend_correction",
            truth_authority="backend_correction",
            detail=None,
            notes=["database-backed tcp validation"],
            raw_payload={},
            checked_at=now,
        )
    )
    repository.commit()

    trade_service = TradeService(
        store,
        download_root=downloads,
        seller_onboarding_repository=repository,
    )
    file_service = FileService(downloads)

    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_trade_service] = lambda: trade_service
    app.dependency_overrides[get_file_service] = lambda: file_service

    client = TestClient(app)

    try:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": "buyer-db@example.com",
                "display_name": "Buyer DB",
                "password": "password123",
                "role": "buyer",
            },
        )
        assert register.status_code == 201, register.text
        token = register.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        order = client.post(
            "/api/v1/orders",
            headers=headers,
            json={
                "offer_id": "offer-medium-gpu",
                "requested_duration_minutes": 60,
            },
        )
        assert order.status_code == 201, order.text

        activation = client.post(f"/api/v1/orders/{order.json()['id']}/activate", headers=headers)
        assert activation.status_code == 200, activation.text
        payload = activation.json()["access_grant"]["connect_material_payload"]
        assert payload["effective_target_addr"] == "10.66.66.10"
        assert payload["effective_target_source"] == "backend_correction"
        assert payload["truth_authority"] == "backend_correction"
        assert payload["minimum_tcp_validation"]["validated_against_effective_target"] is True
    finally:
        db_session.close()
        app.dependency_overrides.clear()
