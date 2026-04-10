from fastapi.testclient import TestClient

from backend_app.api.deps import get_auth_service, get_seller_onboarding_service
from backend_app.clients.adapter_client import AdapterClientError
from backend_app.main import app
from backend_app.services.auth_service import AuthService
from backend_app.services.seller_onboarding_service import SellerOnboardingService
from backend_app.storage.memory_store import InMemoryStore


class FakeAdapterClient:
    def __init__(
        self,
        *,
        node_addr: str,
        expected_wireguard_ip: str | None = "10.0.8.12",
        fail_compute_lookup: bool = False,
        claim_error: AdapterClientError | None = None,
    ) -> None:
        self.node_addr = node_addr
        self.expected_wireguard_ip = expected_wireguard_ip
        self.fail_compute_lookup = fail_compute_lookup
        self.claim_error = claim_error
        self.inspect_calls: list[tuple[str, str]] = []
        self.claim_calls: list[dict[str, str]] = []

    def get_join_material(self, payload: dict[str, str | None]) -> dict[str, object]:
        compute_node_id = payload.get("requested_compute_node_id") or "compute-seller-1"
        seller_user_id = str(payload.get("seller_user_id") or "")
        accelerator = str(payload.get("requested_accelerator") or "gpu")
        return {
            "join_token": "join-token-1",
            "manager_addr": "81.70.52.75",
            "manager_port": 2377,
            "registry_host": "registry.example.com",
            "registry_port": 5000,
            "swarm_join_command": "docker swarm join --token join-token-1 81.70.52.75:2377",
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
        self.inspect_calls.append(("node_ref", node_ref))
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
                "compute_node_id": "compute-seller-1",
                "seller_user_id": "user_fake",
                "accelerator": "gpu",
                "running_tasks": 0,
            },
            "platform_labels": {},
            "raw_labels": {},
            "tasks": [],
            "recent_error_summary": [],
        }

    def inspect_node_by_compute_node_id(self, compute_node_id: str) -> dict[str, object]:
        self.inspect_calls.append(("compute_node_id", compute_node_id))
        if self.fail_compute_lookup:
            raise AdapterClientError(404, "compute_node_id_not_found", {"detail": "compute_node_id_not_found"})
        payload = self.inspect_node(f"node-for-{compute_node_id}")
        payload["node"]["compute_node_id"] = compute_node_id
        return payload

    def claim_node(self, payload: dict[str, str]) -> dict[str, object]:
        self.claim_calls.append(dict(payload))
        if self.claim_error is not None:
            raise self.claim_error
        return {
            "status": "claimed",
            "node": {
                "id": payload["node_ref"],
                "node_addr": self.node_addr,
                "compute_node_id": payload["compute_node_id"],
            },
            "applied_labels": {
                "platform.role": "compute",
                "platform.compute_enabled": "true",
                "platform.compute_node_id": payload["compute_node_id"],
                "platform.seller_user_id": payload["seller_user_id"],
                "platform.accelerator": payload["accelerator"],
            },
        }


def override_services(
    *,
    node_addr: str,
    expected_wireguard_ip: str | None = "10.0.8.12",
    fail_compute_lookup: bool = False,
    claim_error: AdapterClientError | None = None,
) -> FakeAdapterClient:
    store = InMemoryStore()
    adapter = FakeAdapterClient(
        node_addr=node_addr,
        expected_wireguard_ip=expected_wireguard_ip,
        fail_compute_lookup=fail_compute_lookup,
        claim_error=claim_error,
    )
    app.dependency_overrides[get_auth_service] = lambda: AuthService(store)
    app.dependency_overrides[get_seller_onboarding_service] = lambda: SellerOnboardingService(store, adapter)
    return adapter


def register_seller(client: TestClient, *, email: str) -> dict[str, str]:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Seller One",
            "password": "password123",
            "role": "seller",
        },
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_seller_onboarding_happy_path() -> None:
    adapter = override_services(node_addr="10.0.8.12")
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={
                "requested_offer_tier": "medium",
                "requested_accelerator": "gpu",
                "requested_compute_node_id": "compute-seller-1",
            },
        )
        assert create.status_code == 201, create.text
        create_payload = create.json()
        assert create_payload["status"] == "issued"
        assert create_payload["expected_wireguard_ip"] == "10.0.8.12"
        assert create_payload["manager_acceptance"]["status"] == "pending"
        assert create_payload["manager_acceptance"]["matched"] is None
        session_id = create_payload["session_id"]

        host_probe = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/linux-host-probe",
            headers=headers,
            json={
                "reported_phase": "detect",
                "host_name": "seller-host-1",
                "os_name": "linux",
                "distribution_name": "ubuntu",
                "kernel_release": "6.8.0",
                "virtualization_available": True,
                "sudo_available": True,
                "observed_ips": ["192.168.1.10"],
                "notes": ["host-ready"],
            },
        )
        assert host_probe.status_code == 200, host_probe.text
        assert host_probe.json()["status"] == "probing"

        substrate_probe = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/linux-substrate-probe",
            headers=headers,
            json={
                "reported_phase": "install",
                "distribution_name": "ubuntu",
                "kernel_release": "6.8.0",
                "docker_available": True,
                "docker_version": "26.1",
                "wireguard_available": True,
                "gpu_available": True,
                "cpu_cores": 16,
                "memory_gb": 64,
                "disk_free_gb": 512,
                "observed_ips": ["10.0.8.12"],
                "observed_wireguard_ip": "10.0.8.12",
                "observed_advertise_addr": "10.0.8.12",
                "observed_data_path_addr": "10.0.8.12",
                "notes": ["substrate-ready"],
            },
        )
        assert substrate_probe.status_code == 200, substrate_probe.text
        substrate_payload = substrate_probe.json()
        assert substrate_payload["expected_wireguard_ip"] == "10.0.8.12"
        assert substrate_payload["swarm_join_material"]["expected_wireguard_ip"] == "10.0.8.12"
        assert substrate_payload["manager_acceptance"]["status"] == "pending"
        assert substrate_payload["manager_acceptance"]["detail"] == "awaiting_join_complete"

        runtime_probe = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/container-runtime-probe",
            headers=headers,
            json={
                "reported_phase": "install",
                "runtime_name": "docker",
                "runtime_version": "26.1",
                "engine_available": True,
                "image_store_accessible": True,
                "network_ready": True,
                "observed_images": ["registry.example.com/pivot/runtime:python-gpu-v1"],
                "notes": ["container-runtime-ready"],
            },
        )
        assert runtime_probe.status_code == 200, runtime_probe.text
        assert runtime_probe.json()["container_runtime_probe"]["runtime_name"] == "docker"

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={
                "reported_phase": "install",
                "node_ref": "node-1",
                "compute_node_id": "compute-seller-1",
                "observed_wireguard_ip": "10.0.8.12",
                "observed_advertise_addr": "10.0.8.12",
                "observed_data_path_addr": "10.0.8.12",
                "notes": ["join-finished"],
            },
        )
        assert join_complete.status_code == 200, join_complete.text
        payload = join_complete.json()
        assert payload["status"] == "verified"
        assert payload["last_join_complete"]["node_ref"] == "node-1"
        assert payload["last_join_complete"]["observed_wireguard_ip"] == "10.0.8.12"
        assert payload["manager_acceptance"]["status"] == "matched"
        assert payload["manager_acceptance"]["observed_manager_node_addr"] == "10.0.8.12"
        assert payload["manager_acceptance"]["matched"] is True
        assert adapter.inspect_calls[0] == ("compute_node_id", "compute-seller-1")
        assert adapter.claim_calls[0]["node_ref"] == "node-for-compute-seller-1"
        assert adapter.claim_calls[0]["compute_node_id"] == "compute-seller-1"
        assert adapter.claim_calls[0]["seller_user_id"] == payload["seller_user_id"]

        session = client.get(f"/api/v1/seller/onboarding/sessions/{session_id}", headers=headers)
        assert session.status_code == 200, session.text
        session_payload = session.json()
        assert session_payload["status"] == "verified"
        assert session_payload["probe_summary"]["linux_substrate_probe"]["observed_wireguard_ip"] == "10.0.8.12"

        close = client.post(f"/api/v1/seller/onboarding/sessions/{session_id}/close", headers=headers)
        assert close.status_code == 200, close.text
        assert close.json()["status"] == "closed"
    finally:
        app.dependency_overrides.clear()


def test_seller_onboarding_manager_acceptance_mismatch() -> None:
    override_services(node_addr="10.0.8.99")
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-mismatch@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_accelerator": "gpu"},
        )
        assert create.status_code == 201, create.text
        session_id = create.json()["session_id"]

        substrate_probe = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/linux-substrate-probe",
            headers=headers,
            json={
                "distribution_name": "ubuntu",
                "docker_available": True,
                "wireguard_available": True,
                "observed_wireguard_ip": "10.0.8.12",
            },
        )
        assert substrate_probe.status_code == 200, substrate_probe.text
        assert substrate_probe.json()["expected_wireguard_ip"] == "10.0.8.12"

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={"node_ref": "node-2"},
        )
        assert join_complete.status_code == 200, join_complete.text
        payload = join_complete.json()
        assert payload["status"] == "verify_failed"
        assert payload["manager_acceptance"]["status"] == "mismatch"
        assert payload["manager_acceptance"]["matched"] is False
        assert payload["manager_acceptance"]["detail"] == "manager_node_addr_mismatch"
    finally:
        app.dependency_overrides.clear()


def test_runtime_observation_does_not_override_platform_expected_wireguard_ip() -> None:
    override_services(node_addr="10.0.8.12")
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-observation@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_compute_node_id": "compute-seller-1"},
        )
        assert create.status_code == 201, create.text
        session_id = create.json()["session_id"]
        assert create.json()["expected_wireguard_ip"] == "10.0.8.12"

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={
                "reported_phase": "install",
                "compute_node_id": "compute-seller-1",
                "observed_wireguard_ip": "10.9.9.9",
            },
        )
        assert join_complete.status_code == 200, join_complete.text
        payload = join_complete.json()
        assert payload["expected_wireguard_ip"] == "10.0.8.12"
        assert payload["last_join_complete"]["observed_wireguard_ip"] == "10.9.9.9"
        assert payload["manager_acceptance"]["expected_wireguard_ip"] == "10.0.8.12"
        assert payload["manager_acceptance"]["observed_manager_node_addr"] == "10.0.8.12"
        assert payload["manager_acceptance"]["status"] == "matched"
        assert payload["manager_acceptance"]["matched"] is True
    finally:
        app.dependency_overrides.clear()


def test_create_session_uses_request_expected_wireguard_ip_when_adapter_omits_it() -> None:
    override_services(node_addr="10.66.66.10", expected_wireguard_ip=None)
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-request-expected@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={
                "requested_compute_node_id": "temp-seller-20260408033156-node",
                "expected_wireguard_ip": "10.66.66.10",
            },
        )
        assert create.status_code == 201, create.text
        payload = create.json()
        assert payload["expected_wireguard_ip"] == "10.66.66.10"
        assert payload["swarm_join_material"]["expected_wireguard_ip"] == "10.66.66.10"
        assert payload["manager_acceptance"]["expected_wireguard_ip"] == "10.66.66.10"
        assert payload["manager_acceptance"]["status"] == "pending"
    finally:
        app.dependency_overrides.clear()


def test_join_complete_backfills_expected_wireguard_ip_when_no_prior_fact_exists() -> None:
    override_services(node_addr="10.66.66.10", expected_wireguard_ip=None)
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-join-backfill@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_compute_node_id": "temp-seller-join-backfill-node"},
        )
        assert create.status_code == 201, create.text
        payload = create.json()
        assert payload["expected_wireguard_ip"] is None
        assert payload["swarm_join_material"]["expected_wireguard_ip"] is None
        session_id = payload["session_id"]

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={
                "compute_node_id": "temp-seller-join-backfill-node",
                "observed_wireguard_ip": "10.66.66.10",
            },
        )
        assert join_complete.status_code == 200, join_complete.text
        payload = join_complete.json()
        assert payload["status"] == "verified"
        assert payload["expected_wireguard_ip"] == "10.66.66.10"
        assert payload["swarm_join_material"]["expected_wireguard_ip"] == "10.66.66.10"
        assert payload["last_join_complete"]["observed_wireguard_ip"] == "10.66.66.10"
        assert payload["manager_acceptance"]["expected_wireguard_ip"] == "10.66.66.10"
        assert payload["manager_acceptance"]["observed_manager_node_addr"] == "10.66.66.10"
        assert payload["manager_acceptance"]["status"] == "matched"
    finally:
        app.dependency_overrides.clear()


def test_manager_acceptance_falls_back_to_node_ref_after_compute_node_lookup_miss() -> None:
    adapter = override_services(node_addr="10.0.8.12", fail_compute_lookup=True)
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-fallback@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_compute_node_id": "compute-seller-1"},
        )
        assert create.status_code == 201, create.text
        session_id = create.json()["session_id"]

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={
                "compute_node_id": "compute-seller-1",
                "node_ref": "node-fallback-1",
            },
        )
        assert join_complete.status_code == 200, join_complete.text
        payload = join_complete.json()
        assert payload["status"] == "verified"
        assert payload["manager_acceptance"]["status"] == "matched"
        assert adapter.inspect_calls == [
            ("compute_node_id", "compute-seller-1"),
            ("node_ref", "node-fallback-1"),
            ("node_ref", "node-fallback-1"),
        ]
    finally:
        app.dependency_overrides.clear()


def test_join_complete_rejects_nested_runtime_payload() -> None:
    override_services(node_addr="10.0.8.12")
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-nested@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_accelerator": "gpu"},
        )
        assert create.status_code == 201, create.text
        session_id = create.json()["session_id"]

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={
                "local_execution": {"observed_wireguard_ip": "10.0.8.12"},
                "backend_locator": {"node_ref": "node-1"},
            },
        )
        assert join_complete.status_code == 422, join_complete.text
        detail = join_complete.json()["detail"]
        assert any(item["loc"][-1] == "local_execution" for item in detail)
        assert any(item["loc"][-1] == "backend_locator" for item in detail)
    finally:
        app.dependency_overrides.clear()


def test_join_complete_claim_failure_sets_backend_acceptance_failure() -> None:
    adapter = override_services(
        node_addr="10.0.8.12",
        claim_error=AdapterClientError(409, "node_claim_conflict", {"detail": "node_claim_conflict"}),
    )
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-claim-failure@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_compute_node_id": "compute-seller-1"},
        )
        assert create.status_code == 201, create.text
        session_id = create.json()["session_id"]

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={"compute_node_id": "compute-seller-1"},
        )
        assert join_complete.status_code == 200, join_complete.text
        payload = join_complete.json()
        assert payload["status"] == "verify_failed"
        assert payload["manager_acceptance"]["status"] == "claim_failed"
        assert payload["manager_acceptance"]["detail"] == "node_claim_conflict"
        assert adapter.claim_calls[0]["compute_node_id"] == "compute-seller-1"
    finally:
        app.dependency_overrides.clear()


def test_correction_reverify_and_minimum_tcp_validation_close_the_truth_chain() -> None:
    adapter = override_services(node_addr="10.0.8.99")
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-correction@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_compute_node_id": "compute-seller-1"},
        )
        assert create.status_code == 201, create.text
        session_id = create.json()["session_id"]

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={
                "compute_node_id": "compute-seller-1",
                "observed_wireguard_ip": "10.0.8.12",
                "observed_advertise_addr": "10.0.8.99",
                "observed_data_path_addr": "10.0.8.99",
            },
        )
        assert join_complete.status_code == 200, join_complete.text
        mismatch_payload = join_complete.json()
        assert mismatch_payload["status"] == "verify_failed"
        assert mismatch_payload["manager_acceptance"]["status"] == "mismatch"
        assert len(mismatch_payload["manager_acceptance_history"]) == 1
        assert mismatch_payload["manager_acceptance_history"][0]["status"] == "mismatch"

        adapter.node_addr = "10.0.8.12"
        correction = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/corrections",
            headers=headers,
            json={
                "reported_phase": "repair",
                "source_surface": "docker_swarm",
                "correction_action": "set_explicit_advertise_and_data_path_addr",
                "target_wireguard_ip": "10.0.8.12",
                "observed_advertise_addr": "10.0.8.12",
                "observed_data_path_addr": "10.0.8.12",
                "notes": ["operator-correction-recorded"],
            },
        )
        assert correction.status_code == 200, correction.text
        correction_payload = correction.json()
        assert correction_payload["status"] == "joined"
        assert correction_payload["manager_acceptance"]["status"] == "pending"
        assert correction_payload["manager_acceptance"]["detail"] == "awaiting_manager_reverify"
        assert len(correction_payload["correction_history"]) == 1
        assert correction_payload["correction_history"][0]["correction_action"] == "set_explicit_advertise_and_data_path_addr"
        assert correction_payload["minimum_tcp_validation"] is None

        reverify = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/re-verify",
            headers=headers,
            json={"reported_phase": "repair", "notes": ["manager-reverify-after-correction"]},
        )
        assert reverify.status_code == 200, reverify.text
        reverify_payload = reverify.json()
        assert reverify_payload["status"] == "verified"
        assert reverify_payload["manager_acceptance"]["status"] == "matched"
        assert reverify_payload["manager_acceptance"]["observed_manager_node_addr"] == "10.0.8.12"
        assert len(reverify_payload["manager_acceptance_history"]) == 2
        assert reverify_payload["manager_acceptance_history"][-1]["status"] == "matched"

        tcp_validation = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/minimum-tcp-validation",
            headers=headers,
            json={
                "reported_phase": "repair",
                "target_addr": "10.0.8.12",
                "target_port": 8080,
                "reachable": True,
                "notes": ["tcp-validation-passed"],
            },
        )
        assert tcp_validation.status_code == 200, tcp_validation.text
        tcp_payload = tcp_validation.json()
        assert tcp_payload["minimum_tcp_validation"]["target_addr"] == "10.0.8.12"
        assert tcp_payload["minimum_tcp_validation"]["target_port"] == 8080
        assert tcp_payload["minimum_tcp_validation"]["reachable"] is True
        assert tcp_payload["minimum_tcp_validation"]["validated_against_manager_target"] is True
        assert tcp_payload["minimum_tcp_validation"]["detail"] is None
    finally:
        app.dependency_overrides.clear()


def test_minimum_tcp_validation_rejects_unmatched_manager_target_as_ready() -> None:
    override_services(node_addr="10.0.8.99")
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-tcp-mismatch@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_compute_node_id": "compute-seller-1"},
        )
        assert create.status_code == 201, create.text
        session_id = create.json()["session_id"]

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={"compute_node_id": "compute-seller-1"},
        )
        assert join_complete.status_code == 200, join_complete.text
        assert join_complete.json()["manager_acceptance"]["status"] == "mismatch"

        tcp_validation = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/minimum-tcp-validation",
            headers=headers,
            json={
                "target_addr": "10.0.8.12",
                "target_port": 8080,
                "reachable": True,
            },
        )
        assert tcp_validation.status_code == 200, tcp_validation.text
        payload = tcp_validation.json()
        assert payload["status"] == "verify_failed"
        assert payload["minimum_tcp_validation"]["validated_against_manager_target"] is False
        assert payload["minimum_tcp_validation"]["detail"] == "manager_acceptance_not_matched"
    finally:
        app.dependency_overrides.clear()


def test_manager_address_override_exposes_effective_target_and_allows_tcp_validation_against_override() -> None:
    override_services(node_addr="202.113.184.2", expected_wireguard_ip="10.66.66.10")
    client = TestClient(app)

    try:
        headers = register_seller(client, email="seller-override@example.com")

        create = client.post(
            "/api/v1/seller/onboarding/sessions",
            headers=headers,
            json={"requested_compute_node_id": "temp-seller-override-node"},
        )
        assert create.status_code == 201, create.text
        session_id = create.json()["session_id"]

        join_complete = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/join-complete",
            headers=headers,
            json={
                "reported_phase": "repair",
                "compute_node_id": "temp-seller-override-node",
                "observed_wireguard_ip": "10.66.66.10",
                "observed_advertise_addr": "10.66.66.10",
                "observed_data_path_addr": "10.66.66.10",
            },
        )
        assert join_complete.status_code == 200, join_complete.text
        mismatch_payload = join_complete.json()
        assert mismatch_payload["manager_acceptance"]["status"] == "mismatch"
        assert mismatch_payload["effective_target_addr"] is None
        assert mismatch_payload["effective_target_source"] is None

        override_payload = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/manager-address-override",
            headers=headers,
            json={
                "reported_phase": "repair",
                "source_surface": "operator_override",
                "override_target_addr": "10.66.66.10",
                "override_reason": "single-manager override lane for verified WG seller target",
                "notes": ["explicit workflow override"],
            },
        )
        assert override_payload.status_code == 200, override_payload.text
        payload = override_payload.json()
        assert payload["manager_acceptance"]["status"] == "mismatch"
        assert payload["manager_address_override"]["override_target_addr"] == "10.66.66.10"
        assert payload["effective_target_addr"] == "10.66.66.10"
        assert payload["effective_target_source"] == "operator_override"

        tcp_validation = client.post(
            f"/api/v1/seller/onboarding/sessions/{session_id}/minimum-tcp-validation",
            headers=headers,
            json={
                "reported_phase": "repair",
                "target_addr": "10.66.66.10",
                "target_port": 8080,
                "reachable": True,
                "notes": ["override-lane tcp validation"],
            },
        )
        assert tcp_validation.status_code == 200, tcp_validation.text
        tcp_payload = tcp_validation.json()
        assert tcp_payload["minimum_tcp_validation"]["validated_against_manager_target"] is False
        assert tcp_payload["minimum_tcp_validation"]["validated_against_effective_target"] is True
        assert tcp_payload["minimum_tcp_validation"]["effective_target_addr"] == "10.66.66.10"
        assert tcp_payload["minimum_tcp_validation"]["effective_target_source"] == "operator_override"
        assert tcp_payload["minimum_tcp_validation"]["detail"] is None
    finally:
        app.dependency_overrides.clear()
