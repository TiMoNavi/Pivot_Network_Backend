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
        self.assertIn("自然语言", response.text)

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

    def test_stage4_runtime_routes_are_wired(self) -> None:
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
        runtime_session_payload = {
            "runtime_session": {
                "id": "runtime-1",
                "status": "ready",
                "runtime_bundle_status": "running",
            },
            "runtime_access_plan": {
                "runtime_session_id": "runtime-1",
                "network_entry": {
                    "shell_embed_url": "http://10.66.66.1:32080/shell/runtime-1",
                    "workspace_status_url": "http://10.66.66.1:32080/api/workspace/status",
                },
            },
        }

        with (
            patch("buyer_client_app.main.BackendClient.login", return_value=login_payload),
            patch("buyer_client_app.main.create_runtime_session", return_value=runtime_session_payload),
            patch("buyer_client_app.main.refresh_runtime_session", return_value=runtime_session_payload),
            patch(
                "buyer_client_app.main.wireguard_up",
                return_value={"status": "up", "interface_name": "pivot-buyer-runtime-1"},
            ),
            patch(
                "buyer_client_app.main.wireguard_down",
                return_value={"status": "down", "interface_name": "pivot-buyer-runtime-1"},
            ),
            patch(
                "buyer_client_app.main.open_shell",
                return_value={"shell_embed_url": "http://10.66.66.1:32080/shell/runtime-1"},
            ),
            patch(
                "buyer_client_app.main.sync_workspace_selection",
                return_value={"workspace_selection": {"path": "/tmp/workspace"}, "status": {"files": []}},
            ),
            patch(
                "buyer_client_app.main.read_workspace_status",
                return_value={"workspace_root": "/workspace", "files": [{"path": "README.md"}]},
            ),
            patch(
                "buyer_client_app.main.submit_task_execution",
                return_value={"id": "task-1", "status": "succeeded", "exit_code": 0},
            ),
            patch(
                "buyer_client_app.main.tail_task_logs",
                return_value={"task_id": "task-1", "stdout_tail": "ok", "stderr_tail": ""},
            ),
        ):
            login = self.client.post(
                "/local-api/auth/login",
                json={"email": "buyer@example.com", "password": "password123"},
            )
            self.assertEqual(login.status_code, 200, login.text)

            imported = self.client.post(
                "/local-api/access-grants/import-code",
                headers=headers,
                json={"grant_code": "grant-code-12345678"},
            )
            self.assertEqual(imported.status_code, 200, imported.text)
            self.assertEqual(imported.json()["status"], "imported")

            created = self.client.post(
                "/local-api/runtime-sessions/create",
                headers=headers,
                json={"grant_code": "grant-code-12345678"},
            )
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.json()["runtime_session"]["id"], "runtime-1")

            refreshed = self.client.post(
                "/local-api/runtime-sessions/refresh",
                headers=headers,
                json={"runtime_session_id": "runtime-1"},
            )
            self.assertEqual(refreshed.status_code, 200, refreshed.text)

            wg_up = self.client.post("/local-api/wireguard/up", headers=headers)
            self.assertEqual(wg_up.status_code, 200, wg_up.text)
            self.assertEqual(wg_up.json()["status"], "up")

            shell = self.client.post("/local-api/runtime-shell/open", headers=headers)
            self.assertEqual(shell.status_code, 200, shell.text)
            self.assertIn("/shell/runtime-1", shell.json()["shell_embed_url"])

            synced = self.client.post(
                "/local-api/workspace/sync",
                headers=headers,
                json={"path": "/tmp/workspace"},
            )
            self.assertEqual(synced.status_code, 200, synced.text)

            workspace_status = self.client.get("/local-api/workspace/status", headers=headers)
            self.assertEqual(workspace_status.status_code, 200, workspace_status.text)
            self.assertEqual(workspace_status.json()["workspace_root"], "/workspace")

            task = self.client.post(
                "/local-api/tasks/submit",
                headers=headers,
                json={"command": "pwd"},
            )
            self.assertEqual(task.status_code, 200, task.text)
            self.assertEqual(task.json()["id"], "task-1")

            logs = self.client.get("/local-api/tasks/task-1/logs", headers=headers)
            self.assertEqual(logs.status_code, 200, logs.text)
            self.assertEqual(logs.json()["stdout_tail"], "ok")

            wg_down = self.client.post("/local-api/wireguard/down", headers=headers)
            self.assertEqual(wg_down.status_code, 200, wg_down.text)
            self.assertEqual(wg_down.json()["status"], "down")

    def test_stage5_assistant_route_is_wired(self) -> None:
        headers = self._window_headers()
        with patch(
            "buyer_client_app.main.execute_assistant_request",
            return_value={"ok": True, "assistant_message": "buyer stage5 ok"},
        ) as assistant:
            response = self.client.post(
                "/local-api/assistant/message",
                headers=headers,
                json={"message": "使用当前 grant 建立会话并执行 `pwd`"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["assistant_message"], "buyer stage5 ok")
        assistant.assert_called_once()


if __name__ == "__main__":
    unittest.main()
