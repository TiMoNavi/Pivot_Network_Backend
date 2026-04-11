from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from backend_app.api.deps import get_auth_service, get_file_service, get_trade_service
from backend_app.main import app
from backend_app.services.auth_service import AuthService
from backend_app.services.file_service import FileService
from backend_app.services.trade_service import TradeService
from backend_app.storage.memory_store import InMemoryStore


class FakeRuntimeAdapterClient:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}

    def _bundle_payload(self, session_id: str, public_key: str, status: str) -> dict:
        return {
            "session_id": session_id,
            "status": status,
            "runtime_service_name": f"runtime-{session_id}",
            "gateway_service_name": f"gateway-{session_id}",
            "network_name": f"pivot-session-{session_id}",
            "connect_metadata": {
                "wireguard_shell_embed_url": f"http://10.66.66.1:32080/shell/{session_id}",
                "workspace_sync_url": f"http://10.66.66.1:32080/api/workspace/upload/{session_id}",
            },
            "wireguard_lease_metadata": {
                "runtime_session_id": session_id,
                "lease_type": "buyer",
                "status": "applied",
                "public_key": public_key,
                "client_address": "10.66.66.200",
                "server_interface": "wg0",
                "server_public_key": "server-public-key",
                "server_access_ip": "10.66.66.1",
                "endpoint_host": "81.70.52.75",
                "endpoint_port": 51820,
                "allowed_ips": ["10.66.66.200/32"],
                "client_allowed_ips": ["10.66.66.1/32"],
                "persistent_keepalive": 25,
                "lease_payload": {},
            },
            "recent_error_summary": [],
        }

    def create_runtime_session_bundle(self, payload: dict) -> dict:
        session_id = payload["session_id"]
        public_key = payload["buyer_network"]["public_key"]
        self.sessions[session_id] = self._bundle_payload(session_id, public_key, "running")
        return self._bundle_payload(session_id, public_key, "provisioning")

    def inspect_runtime_session_bundle(self, payload: dict) -> dict:
        session_id = payload["session_id"]
        return self.sessions.get(session_id, self._bundle_payload(session_id, "buyer-public-key", "running"))

    def remove_runtime_session_bundle(self, payload: dict) -> dict:
        session_id = payload["session_id"]
        existing = self.sessions.pop(session_id, None)
        return {
            "session_id": session_id,
            "status": "removed",
            "runtime_service_name": f"runtime-{session_id}",
            "gateway_service_name": f"gateway-{session_id}",
            "network_name": f"pivot-session-{session_id}",
            "connect_metadata": {},
            "wireguard_lease_metadata": {
                "runtime_session_id": session_id,
                "lease_type": "buyer",
                "status": "removed",
                "public_key": None if existing is None else existing["wireguard_lease_metadata"]["public_key"],
            },
            "recent_error_summary": [],
        }


def _override_services(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    store = InMemoryStore()
    store.seed_offers()
    auth_service = AuthService(store)
    trade_service = TradeService(
        store,
        download_root=downloads,
        adapter_client=FakeRuntimeAdapterClient(),
    )
    file_service = FileService(downloads)

    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_trade_service] = lambda: trade_service
    app.dependency_overrides[get_file_service] = lambda: file_service


def test_redeem_access_grant_creates_runtime_session_by_id(tmp_path: Path) -> None:
    _override_services(tmp_path)
    client = TestClient(app)
    try:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": "buyer-runtime-id@example.com",
                "display_name": "Buyer Runtime",
                "password": "password123",
                "role": "buyer",
            },
        )
        token = register.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        order = client.post(
            "/api/v1/orders",
            headers=headers,
            json={"offer_id": "offer-medium-gpu", "requested_duration_minutes": 60},
        )
        order_id = order.json()["id"]
        activation = client.post(f"/api/v1/orders/{order_id}/activate", headers=headers)
        grant = activation.json()["access_grant"]

        redeem = client.post(
            "/api/v1/access-grants/redeem",
            headers=headers,
            json={
                "grant_id": grant["grant_id"],
                "wireguard_public_key": "buyer-public-key",
            },
        )
        assert redeem.status_code == 200, redeem.text
        payload = redeem.json()
        assert payload["access_grant_id"] == grant["grant_id"]
        assert payload["status"] == "ready"
        assert payload["runtime_bundle_status"] == "running"
        assert payload["connect_metadata"]["wireguard_shell_embed_url"]
        assert payload["wireguard_lease_metadata"]["status"] == "applied"

        runtime_session = client.get(f"/api/v1/runtime-sessions/{payload['id']}", headers=headers)
        assert runtime_session.status_code == 200, runtime_session.text
        assert runtime_session.json()["id"] == payload["id"]
        assert runtime_session.json()["status"] == "ready"
    finally:
        app.dependency_overrides.clear()


def test_redeem_access_grant_by_code_reuses_same_real_grant(tmp_path: Path) -> None:
    _override_services(tmp_path)
    client = TestClient(app)
    try:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": "buyer-runtime-code@example.com",
                "display_name": "Buyer Runtime Code",
                "password": "password123",
                "role": "buyer",
            },
        )
        token = register.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        order = client.post(
            "/api/v1/orders",
            headers=headers,
            json={"offer_id": "offer-medium-gpu", "requested_duration_minutes": 60},
        )
        order_id = order.json()["id"]
        activation = client.post(f"/api/v1/orders/{order_id}/activate", headers=headers)
        grant = activation.json()["access_grant"]

        redeem = client.post(
            "/api/v1/access-grants/redeem-by-code",
            headers=headers,
            json={
                "grant_code": grant["grant_code"],
                "wireguard_public_key": "buyer-public-key",
            },
        )
        assert redeem.status_code == 200, redeem.text
        payload = redeem.json()
        assert payload["access_grant_id"] == grant["grant_id"]
        assert payload["status"] == "ready"
    finally:
        app.dependency_overrides.clear()


def test_redeemed_grant_remains_visible_with_runtime_bootstrap_in_active_list(tmp_path: Path) -> None:
    _override_services(tmp_path)
    client = TestClient(app)
    try:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": "buyer-runtime-active@example.com",
                "display_name": "Buyer Runtime Active",
                "password": "password123",
                "role": "buyer",
            },
        )
        token = register.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        order = client.post(
            "/api/v1/orders",
            headers=headers,
            json={"offer_id": "offer-medium-gpu", "requested_duration_minutes": 60},
        )
        activation = client.post(f"/api/v1/orders/{order.json()['id']}/activate", headers=headers)
        grant = activation.json()["access_grant"]

        redeem = client.post(
            "/api/v1/access-grants/redeem",
            headers=headers,
            json={"grant_id": grant["grant_id"], "wireguard_public_key": "buyer-public-key"},
        )
        session_id = redeem.json()["id"]

        active = client.get("/api/v1/me/access-grants/active", headers=headers)
        assert active.status_code == 200, active.text
        assert active.json()["total"] == 1
        listed_grant = active.json()["items"][0]
        assert listed_grant["status"] == "redeemed"
        assert listed_grant["runtime_session_id"] == session_id
        assert listed_grant["connect_material_payload"]["runtime_session_id"] == session_id
        assert listed_grant["connect_material_payload"]["wireguard_shell_embed_url"]
        assert listed_grant["connect_material_payload"]["workspace_sync_url"]
        assert listed_grant["connect_material_payload"]["server_public_key"] == "server-public-key"
    finally:
        app.dependency_overrides.clear()


def test_runtime_session_lifecycle_routes_exist_for_stage4_surface(tmp_path: Path) -> None:
    _override_services(tmp_path)
    client = TestClient(app)
    try:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": "buyer-runtime-lifecycle@example.com",
                "display_name": "Buyer Runtime Lifecycle",
                "password": "password123",
                "role": "buyer",
            },
        )
        token = register.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        order = client.post(
            "/api/v1/orders",
            headers=headers,
            json={"offer_id": "offer-medium-gpu", "requested_duration_minutes": 60},
        )
        activation = client.post(f"/api/v1/orders/{order.json()['id']}/activate", headers=headers)
        redeem = client.post(
            "/api/v1/access-grants/redeem",
            headers=headers,
            json={"grant_id": activation.json()["access_grant"]["grant_id"], "wireguard_public_key": "buyer-public-key"},
        )
        session_id = redeem.json()["id"]

        heartbeat = client.post(f"/api/v1/runtime-sessions/{session_id}/heartbeat", headers=headers)
        assert heartbeat.status_code == 200, heartbeat.text
        assert heartbeat.json()["status"] == "ready"

        close = client.post(f"/api/v1/runtime-sessions/{session_id}/close", headers=headers)
        assert close.status_code == 200, close.text
        assert close.json()["status"] == "closed"
        assert close.json()["runtime_bundle_status"] == "removed"
    finally:
        app.dependency_overrides.clear()


def test_redeem_reprovisions_ready_session_when_wireguard_key_changes(tmp_path: Path) -> None:
    _override_services(tmp_path)
    client = TestClient(app)
    try:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": "buyer-runtime-key-refresh@example.com",
                "display_name": "Buyer Runtime Key Refresh",
                "password": "password123",
                "role": "buyer",
            },
        )
        token = register.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        order = client.post(
            "/api/v1/orders",
            headers=headers,
            json={"offer_id": "offer-medium-gpu", "requested_duration_minutes": 60},
        )
        activation = client.post(f"/api/v1/orders/{order.json()['id']}/activate", headers=headers)
        grant = activation.json()["access_grant"]

        first = client.post(
            "/api/v1/access-grants/redeem",
            headers=headers,
            json={"grant_id": grant["grant_id"], "wireguard_public_key": "buyer-public-key-1"},
        )
        assert first.status_code == 200, first.text
        first_payload = first.json()

        second = client.post(
            "/api/v1/access-grants/redeem",
            headers=headers,
            json={"grant_id": grant["grant_id"], "wireguard_public_key": "buyer-public-key-2"},
        )
        assert second.status_code == 200, second.text
        second_payload = second.json()

        assert second_payload["id"] == first_payload["id"]
        assert second_payload["wireguard_lease_metadata"]["public_key"] == "buyer-public-key-2"

        runtime_session = client.get(f"/api/v1/runtime-sessions/{second_payload['id']}", headers=headers)
        assert runtime_session.status_code == 200, runtime_session.text
        assert runtime_session.json()["wireguard_lease_metadata"]["public_key"] == "buyer-public-key-2"
    finally:
        app.dependency_overrides.clear()
