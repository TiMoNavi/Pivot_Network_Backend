from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from backend_app.core.config import get_settings
from backend_app.main import app
from backend_app.api.routes.seller import get_seller_onboarding_service


def _register_seller(client: TestClient) -> str:
    unique = uuid4().hex
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"seller-{unique}@example.com",
            "display_name": f"Seller {unique[:8]}",
            "role": "seller",
            "password": "SellerPass123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def test_seller_onboarding_lifecycle(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_SELLER_CODEX_OPENAI_API_KEY", "test-seller-key")
    get_settings.cache_clear()
    client = TestClient(app)
    token = _register_seller(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/api/v1/seller/onboarding/sessions",
        headers=headers,
        json={
            "requested_accelerator": "gpu",
            "requested_compute_node_id": f"compute-{uuid4().hex[:8]}",
        },
    )
    assert create_response.status_code == 201, create_response.text
    session_payload = create_response.json()
    session_id = session_payload["session_id"]
    assert session_payload["status"] == "active"
    assert session_payload["policy"]["allowed_runtime_base_image"]

    bootstrap_response = client.get(
        f"/api/v1/seller/onboarding/sessions/{session_id}/bootstrap-config",
        headers=headers,
    )
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    bootstrap_payload = bootstrap_response.json()
    assert "model_provider" in bootstrap_payload["codex_config_toml"]
    assert "OPENAI_API_KEY" in bootstrap_payload["codex_auth_json"]
    assert bootstrap_payload["mcp_launch"]["transport"] == "stdio"
    assert bootstrap_payload["window_session_scope"] == "browser_window"

    ubuntu_bootstrap_response = client.get(
        f"/api/v1/seller/onboarding/sessions/{session_id}/ubuntu-bootstrap",
        headers=headers,
    )
    assert ubuntu_bootstrap_response.status_code == 200, ubuntu_bootstrap_response.text
    ubuntu_bootstrap = ubuntu_bootstrap_response.json()
    assert ubuntu_bootstrap["ubuntu_compute_bootstrap"]["seller_swarm_standard_image"]["image_ref"]
    assert ubuntu_bootstrap["ubuntu_compute_bootstrap"]["seller_swarm_standard_image"]["pull_command"].startswith("docker pull ")
    assert ubuntu_bootstrap["ubuntu_compute_bootstrap"]["expected_node_addr"] == "10.66.66.11"

    env_report_response = client.post(
        f"/api/v1/seller/onboarding/sessions/{session_id}/env-report",
        headers=headers,
        json={"env_report": {"summary": {"passed": 3, "failed": 0}, "checks": []}},
    )
    assert env_report_response.status_code == 200, env_report_response.text
    assert env_report_response.json()["last_env_report"]["summary"]["passed"] == 3

    heartbeat_response = client.post(
        f"/api/v1/seller/onboarding/sessions/{session_id}/heartbeat",
        headers=headers,
    )
    assert heartbeat_response.status_code == 200, heartbeat_response.text
    assert heartbeat_response.json()["status"] == "active"

    close_response = client.post(
        f"/api/v1/seller/onboarding/sessions/{session_id}/close",
        headers=headers,
    )
    assert close_response.status_code == 200, close_response.text
    assert close_response.json()["status"] == "closed"

    get_settings.cache_clear()


def test_seller_claim_route_can_be_overridden() -> None:
    client = TestClient(app)
    token = _register_seller(client)
    headers = {"Authorization": f"Bearer {token}"}

    class FakeOnboardingService:
        def claim_node(self, seller_user_id, node_ref: str, payload):  # noqa: ANN001
            return {
                "status": "claimed",
                "node_ref": node_ref,
                "seller_user_id": str(seller_user_id),
                "compute_node_id": payload.compute_node_id,
            }

    app.dependency_overrides[get_seller_onboarding_service] = lambda: FakeOnboardingService()
    try:
        response = client.post(
            "/api/v1/seller/nodes/local-node/claim",
            headers=headers,
            json={
                "onboarding_session_id": "session-test",
                "compute_node_id": "compute-test",
                "requested_accelerator": "gpu",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "claimed"
    assert payload["node_ref"] == "local-node"
