from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from backend_app.api.routes.buyer import get_buyer_runtime_client_service
from backend_app.main import app


def _register_buyer(client: TestClient) -> str:
    unique = uuid4().hex
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"buyer-{unique}@example.com",
            "display_name": f"Buyer {unique[:8]}",
            "role": "buyer",
            "password": "BuyerPass123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def test_buyer_runtime_client_routes_can_be_overridden() -> None:
    client = TestClient(app)
    token = _register_buyer(client)
    headers = {"Authorization": f"Bearer {token}"}

    class FakeBuyerRuntimeClientService:
        def get_bootstrap_config(self, buyer_user_id, session_id: str):  # noqa: ANN001
            now = datetime.now(UTC)
            return {
                "runtime_session_id": session_id,
                "client_session": {
                    "status": "active",
                    "expires_at": now + timedelta(minutes=30),
                    "last_heartbeat_at": now,
                    "last_env_report": None,
                },
                "codex_config_toml": 'model_provider = "OpenAI"\n',
                "codex_auth_json": '{"OPENAI_API_KEY":"test"}',
                "codex_mcp_launch": {"name": "buyer-client-tools", "transport": "stdio", "command": ["python"]},
                "shell_embed_url": "http://10.66.66.1:32080/shell/",
                "public_gateway_access_url": "http://81.70.52.75:32080/",
                "wireguard_gateway_access_url": "http://10.66.66.1:32080/",
                "workspace_sync_url": "http://10.66.66.1:32080/api/workspace/upload",
                "workspace_root": "/workspace",
                "wireguard_profile": {
                    "server_public_key": "server-pub",
                    "client_address": "10.66.66.200",
                    "endpoint_host": "81.70.52.75",
                    "endpoint_port": 45182,
                    "allowed_ips": ["10.66.66.1/32"],
                    "persistent_keepalive": 25,
                },
            }

        def get_client_session(self, buyer_user_id, session_id: str):  # noqa: ANN001
            now = datetime.now(UTC)
            return {
                "status": "active",
                "expires_at": now + timedelta(minutes=30),
                "last_heartbeat_at": now,
                "last_env_report": None,
            }

        def report_env(self, buyer_user_id, session_id: str, env_report: dict):  # noqa: ANN001
            now = datetime.now(UTC)
            return {
                "status": "active",
                "expires_at": now + timedelta(minutes=30),
                "last_heartbeat_at": now,
                "last_env_report": env_report,
            }

        def heartbeat(self, buyer_user_id, session_id: str):  # noqa: ANN001
            now = datetime.now(UTC)
            return {
                "status": "active",
                "expires_at": now + timedelta(minutes=30),
                "last_heartbeat_at": now,
                "last_env_report": None,
            }

        def close(self, buyer_user_id, session_id: str):  # noqa: ANN001
            now = datetime.now(UTC)
            return {
                "status": "closed",
                "expires_at": now + timedelta(minutes=30),
                "last_heartbeat_at": now,
                "last_env_report": None,
            }

    app.dependency_overrides[get_buyer_runtime_client_service] = lambda: FakeBuyerRuntimeClientService()
    try:
        bootstrap = client.get("/api/v1/buyer/runtime-sessions/runtime-test/bootstrap-config", headers=headers)
        assert bootstrap.status_code == 200, bootstrap.text
        payload = bootstrap.json()
        assert payload["runtime_session_id"] == "runtime-test"
        assert payload["wireguard_profile"]["allowed_ips"] == ["10.66.66.1/32"]

        env_report = client.post(
            "/api/v1/buyer/runtime-sessions/runtime-test/env-report",
            headers=headers,
            json={"env_report": {"summary": {"passed": 4}, "checks": []}},
        )
        assert env_report.status_code == 200, env_report.text
        assert env_report.json()["last_env_report"]["summary"]["passed"] == 4

        heartbeat = client.post("/api/v1/buyer/runtime-sessions/runtime-test/heartbeat", headers=headers)
        assert heartbeat.status_code == 200, heartbeat.text
        assert heartbeat.json()["status"] == "active"

        close = client.post("/api/v1/buyer/runtime-sessions/runtime-test/close", headers=headers)
        assert close.status_code == 200, close.text
        assert close.json()["status"] == "closed"
    finally:
        app.dependency_overrides.clear()
