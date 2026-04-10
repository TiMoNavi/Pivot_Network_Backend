from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend_app.api.deps import (
    get_auth_service,
    get_capability_assessment_service,
    get_file_service,
    get_seller_onboarding_service,
    get_trade_service,
)
from backend_app.db.base import Base
from backend_app.main import app
from backend_app.repositories.seller_onboarding_repository import SellerOnboardingRepository
from backend_app.repositories.trade_repository import TradeRepository
from backend_app.services.auth_service import AuthService
from backend_app.services.capability_assessment_service import CapabilityAssessmentService
from backend_app.services.file_service import FileService
from backend_app.services.offer_commercialization_service import OfferCommercializationService
from backend_app.services.seller_onboarding_service import SellerOnboardingService
from backend_app.services.trade_service import TradeService
from backend_app.storage.memory_store import InMemoryStore


class CapabilityFakeAdapterClient:
    def __init__(self) -> None:
        self.expected_wireguard_ip = "10.0.8.12"
        self.node_addr = "10.0.8.12"
        self.probe_status = "probed"
        self.validation_status = "validated"
        self.compute_node_id = "compute-seller-1"

    def get_join_material(self, payload: dict[str, str | None]) -> dict[str, object]:
        compute_node_id = payload.get("requested_compute_node_id") or self.compute_node_id
        seller_user_id = str(payload.get("seller_user_id") or "")
        accelerator = str(payload.get("requested_accelerator") or "gpu")
        return {
            "join_token": "join-token-1",
            "manager_addr": "10.66.66.1",
            "manager_port": 2377,
            "registry_host": "registry.example.com",
            "registry_port": 5000,
            "swarm_join_command": "docker swarm join --token join-token-1 10.66.66.1:2377",
            "claim_required": True,
            "recommended_compute_node_id": compute_node_id,
            "expected_wireguard_ip": self.expected_wireguard_ip,
            "recommended_labels": {
                "platform.role": "compute",
                "platform.compute_enabled": "true",
                "platform.compute_node_id": compute_node_id,
                "platform.seller_user_id": seller_user_id,
                "platform.accelerator": accelerator,
            },
            "next_step": "seller_host_runs_join_then_backend_calls_claim",
        }

    def inspect_node(self, node_ref: str) -> dict[str, object]:
        return {
            "node": {
                "id": node_ref,
                "hostname": "seller-node-1",
                "role": "worker",
                "status": "ready",
                "availability": "active",
                "node_addr": self.node_addr,
                "platform_role": "compute",
                "compute_enabled": True,
                "compute_node_id": self.compute_node_id,
                "seller_user_id": "user_fake",
                "accelerator": "gpu",
                "running_tasks": 1,
            },
            "platform_labels": {},
            "raw_labels": {},
            "tasks": [{"name": "runtime-task", "desired_state": "running", "current_state": "running"}],
            "recent_error_summary": [],
        }

    def inspect_node_by_compute_node_id(self, compute_node_id: str) -> dict[str, object]:
        self.compute_node_id = compute_node_id
        payload = self.inspect_node(f"node-for-{compute_node_id}")
        payload["node"]["compute_node_id"] = compute_node_id
        return payload

    def claim_node(self, payload: dict[str, str]) -> dict[str, object]:
        self.compute_node_id = payload["compute_node_id"]
        return {
            "status": "claimed",
            "node": {
                "id": payload["node_ref"],
                "node_addr": self.node_addr,
                "compute_node_id": payload["compute_node_id"],
            },
            "applied_labels": {
                "platform.compute_node_id": payload["compute_node_id"],
                "platform.seller_user_id": payload["seller_user_id"],
                "platform.accelerator": payload["accelerator"],
            },
        }

    def probe_node(self, payload: dict[str, object]) -> dict[str, object]:
        compute_node_id = str(payload.get("compute_node_id") or self.compute_node_id)
        return {
            "node": {
                "node_id": str(payload.get("node_ref") or f"node-for-{compute_node_id}"),
                "hostname": "seller-node-1",
                "role": "worker",
                "status": "ready",
                "availability": "active",
                "compute_node_id": compute_node_id,
            },
            "probe_status": self.probe_status,
            "probe_measured_capabilities": {
                "cpu_logical": 16,
                "memory_total_mb": 65536,
                "generic_resources": [],
                "accelerator_label": "gpu",
                "host_probe": {"gpu": {"present": True}},
                "probe_source": "docker_node_inspect",
            },
            "warnings": [],
        }

    def validate_runtime_image(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "image_ref": str(payload["image_ref"]),
            "node": {
                "node_id": str(payload.get("node_ref") or f"node-for-{self.compute_node_id}"),
                "hostname": "seller-node-1",
                "role": "worker",
                "status": "ready",
                "availability": "active",
                "compute_node_id": self.compute_node_id,
            },
            "validation_status": self.validation_status,
            "checks": [],
            "validation_payload": {"managed_runtime_image_ok": self.validation_status == "validated"},
        }


def override_full_backend(tmp_path: Path, adapter: CapabilityFakeAdapterClient) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    store = InMemoryStore()
    auth_service = AuthService(store)
    file_service = FileService(downloads)

    temp_dir = Path(tempfile.mkdtemp(prefix="capability-assessment-db-"))
    engine = create_engine(
        f"sqlite+pysqlite:///{temp_dir / 'backend.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_file_service] = lambda: file_service

    def capability_override():
        session = session_local()
        try:
            onboarding_repository = SellerOnboardingRepository(session)
            trade_repository = TradeRepository(session)
            commercialization_service = OfferCommercializationService(trade_repository)
            yield CapabilityAssessmentService(
                onboarding_repository,
                trade_repository,
                adapter,
                commercialization_service,
            )
        finally:
            session.close()

    def onboarding_override():
        session = session_local()
        try:
            onboarding_repository = SellerOnboardingRepository(session)
            trade_repository = TradeRepository(session)
            commercialization_service = OfferCommercializationService(trade_repository)
            capability_service = CapabilityAssessmentService(
                onboarding_repository,
                trade_repository,
                adapter,
                commercialization_service,
            )
            yield SellerOnboardingService(onboarding_repository, adapter, capability_service)
        finally:
            session.close()

    def trade_override():
        session = session_local()
        try:
            yield TradeService(
                None,
                download_root=downloads,
                seller_onboarding_repository=SellerOnboardingRepository(session),
                trade_repository=TradeRepository(session),
            )
        finally:
            session.close()

    app.dependency_overrides[get_capability_assessment_service] = capability_override
    app.dependency_overrides[get_seller_onboarding_service] = onboarding_override
    app.dependency_overrides[get_trade_service] = trade_override


def register_seller(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Seller One",
            "password": "password123",
            "role": "seller",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_session(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/seller/onboarding/sessions",
        headers=headers,
        json={
            "requested_offer_tier": "medium",
            "requested_accelerator": "gpu",
            "requested_compute_node_id": "compute-seller-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def test_verified_onboarding_auto_creates_real_offer(tmp_path: Path) -> None:
    adapter = CapabilityFakeAdapterClient()
    override_full_backend(tmp_path, adapter)
    client = TestClient(app)

    try:
        headers = register_seller(client, "seller-auto-offer@example.com")
        session_id = create_session(client, headers)

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={"compute_node_id": "compute-seller-1", "node_ref": "node-1"},
        )
        assert join_complete.status_code == 200, join_complete.text
        assert join_complete.json()["status"] == "verified"

        offers = client.get("/api/v1/offers")
        assert offers.status_code == 200, offers.text
        payload = offers.json()
        assert payload["total"] == 1
        offer = payload["items"][0]
        assert offer["compute_node_id"] == "compute-seller-1"
        assert offer["status"] == "listed"
        assert offer["price_snapshot"]["hourly_price"] == 12.5
        assert offer["capability_summary"]["accelerator"] == "gpu"
    finally:
        app.dependency_overrides.clear()


def test_capability_assessment_endpoint_is_dry_run_by_default(tmp_path: Path) -> None:
    adapter = CapabilityFakeAdapterClient()
    override_full_backend(tmp_path, adapter)
    client = TestClient(app)

    try:
        headers = register_seller(client, "seller-dry-run@example.com")
        create_session(client, headers)

        assessment = client.post(
            "/api/v1/seller/capability-assessments",
            headers=headers,
            json={"compute_node_id": "compute-seller-1"},
        )
        assert assessment.status_code == 201, assessment.text
        payload = assessment.json()
        assert payload["assessment_status"] == "sellable"
        assert payload["resolved_target"]["compute_node_id"] == "compute-seller-1"
        assert payload["recommended_offer"]["publishable"] is True

        offers = client.get("/api/v1/offers")
        assert offers.status_code == 200, offers.text
        assert offers.json()["total"] == 0
    finally:
        app.dependency_overrides.clear()


def test_invalid_runtime_reassessment_downlists_existing_offer(tmp_path: Path) -> None:
    adapter = CapabilityFakeAdapterClient()
    override_full_backend(tmp_path, adapter)
    client = TestClient(app)

    try:
        headers = register_seller(client, "seller-downlist@example.com")
        session_id = create_session(client, headers)

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={"compute_node_id": "compute-seller-1", "node_ref": "node-1"},
        )
        assert join_complete.status_code == 200, join_complete.text
        assert join_complete.json()["status"] == "verified"

        listed = client.get("/api/v1/offers")
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1
        offer_id = listed.json()["items"][0]["id"]

        adapter.validation_status = "validation_failed"
        tcp_validation = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/minimum-tcp-validation",
            headers=headers,
            json={"target_addr": "10.0.8.12", "target_port": 8080, "reachable": True},
        )
        assert tcp_validation.status_code == 200, tcp_validation.text
        assert tcp_validation.json()["status"] == "verified"

        listed_after = client.get("/api/v1/offers")
        assert listed_after.status_code == 200, listed_after.text
        assert listed_after.json()["total"] == 0

        unavailable_offer = client.get(f"/api/v1/offers/{offer_id}")
        assert unavailable_offer.status_code == 200, unavailable_offer.text
        assert unavailable_offer.json()["status"] == "unavailable"
        assert unavailable_offer.json()["inventory_state"]["assessment_status"] == "runtime_image_invalid"
    finally:
        app.dependency_overrides.clear()
