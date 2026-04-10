from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.main import app, state


class BuyerAppTests(unittest.TestCase):
    def setUp(self) -> None:
        state.reset_for_tests()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        state.reset_for_tests()

    def _window_headers(self) -> dict[str, str]:
        payload = self.client.post("/local-api/window-session/open", json={}).json()
        return {"X-Window-Session-Id": payload["session_id"]}

    def test_root_returns_buyer_page(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("买家本地客户端", response.text)
        self.assertIn("Docker Swarm", response.text)
        self.assertIn("runtime bundle", response.text)

    def test_login_order_activate_flow_uses_runtime_bundle_semantics(self) -> None:
        headers = self._window_headers()
        login_payload = {
            "access_token": "token-1",
            "expires_at": "2026-04-11T00:00:00Z",
            "user": {
                "id": "buyer-1",
                "email": "buyer@example.com",
                "display_name": "Buyer One",
                "role": "buyer",
                "status": "active",
                "created_at": "2026-04-10T00:00:00Z",
                "updated_at": "2026-04-10T00:00:00Z",
            },
        }
        offers_payload = {
            "items": [
                {
                    "id": "offer-medium-gpu",
                    "title": "Medium GPU Runtime",
                    "status": "listed",
                    "seller_user_id": "seller-1",
                    "seller_node_id": "node-1",
                    "offer_profile_id": "profile-1",
                    "runtime_image_ref": "registry.example.com/pivot/runtime:python-gpu-v1",
                    "price_snapshot": {"currency": "CNY", "hourly_price": 12.5},
                    "capability_summary": {"cpu_limit": 8, "memory_limit_gb": 32, "gpu_mode": "shared"},
                    "inventory_state": {"available": True},
                    "published_at": "2026-04-10T00:00:00Z",
                    "updated_at": "2026-04-10T00:00:00Z",
                }
            ],
            "total": 1,
        }
        order_payload = {
            "id": "order-1",
            "buyer_user_id": "buyer-1",
            "offer_id": "offer-medium-gpu",
            "status": "created",
            "requested_duration_minutes": 60,
            "price_snapshot": {"currency": "CNY", "hourly_price": 12.5},
            "runtime_bundle_status": "placeholder_pending",
            "access_grant_id": None,
            "created_at": "2026-04-10T00:00:00Z",
            "updated_at": "2026-04-10T00:00:00Z",
        }
        activation_payload = {
            "order": {
                **order_payload,
                "status": "grant_issued",
                "access_grant_id": "grant-1",
            },
            "access_grant": {
                "id": "grant-1",
                "buyer_user_id": "buyer-1",
                "order_id": "order-1",
                "runtime_session_id": "runtime-order-1",
                "status": "issued",
                "grant_type": "placeholder",
                "connect_material_payload": {
                    "grant_mode": "effective_target_available",
                    "effective_target_addr": "10.66.66.10",
                    "effective_target_source": "backend_correction",
                    "truth_authority": "backend_correction",
                },
                "issued_at": "2026-04-10T00:01:00Z",
                "expires_at": "2026-04-10T12:01:00Z",
                "activated_at": None,
                "revoked_at": None,
            },
        }

        with (
            patch("buyer_client_app.main.BackendClient.login", return_value=login_payload),
            patch("buyer_client_app.main.BackendClient.list_offers", return_value=offers_payload),
            patch("buyer_client_app.main.BackendClient.create_order", return_value=order_payload),
            patch("buyer_client_app.main.BackendClient.activate_order", return_value=activation_payload),
        ):
            login = self.client.post(
                "/local-api/auth/login",
                json={"email": "buyer@example.com", "password": "password123"},
            )
            self.assertEqual(login.status_code, 200, login.text)

            offers = self.client.get("/local-api/offers", headers=headers)
            self.assertEqual(offers.status_code, 200, offers.text)
            self.assertEqual(offers.json()["total"], 1)

            order = self.client.post(
                "/local-api/orders",
                headers=headers,
                json={"offer_id": "offer-medium-gpu", "requested_duration_minutes": 60},
            )
            self.assertEqual(order.status_code, 200, order.text)
            self.assertEqual(order.json()["runtime_access_plan"]["status"], "await_order_activation")

            activated = self.client.post("/local-api/orders/order-1/activate", headers=headers)
            self.assertEqual(activated.status_code, 200, activated.text)
            activated_payload = activated.json()
            self.assertEqual(activated_payload["runtime_access_plan"]["purchase_semantics"], "runtime_bundle")
            self.assertEqual(activated_payload["runtime_access_plan"]["status"], "pending_runtime_bundle")
            self.assertEqual(
                activated_payload["runtime_access_plan"]["truth_lane"]["effective_target_source"],
                "backend_correction",
            )

            current = self.client.get("/local-api/runtime/current", headers=headers)
            self.assertEqual(current.status_code, 200, current.text)
            self.assertEqual(current.json()["current_access_grant"]["id"], "grant-1")


if __name__ == "__main__":
    unittest.main()
