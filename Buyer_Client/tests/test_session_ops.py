from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.config import Settings
from buyer_client_app.errors import LocalAppError
from buyer_client_app.session_ops import create_runtime_session, wireguard_up
from buyer_client_app.state import BuyerClientState


class SessionOpsWireGuardTests(unittest.TestCase):
    def _seed_runtime_state(self, tmpdir: str) -> tuple[Settings, BuyerClientState]:
        settings = Settings(non_windows_workspace_root=tmpdir)
        state = BuyerClientState(settings)
        order = {"id": "order-1", "offer_id": "offer-1", "status": "session_active"}
        grant = {"id": "grant-1", "order_id": "order-1", "runtime_session_id": "runtime-1", "status": "redeemed"}
        runtime_plan = {
            "runtime_session_id": "runtime-1",
            "network_entry": {
                "wireguard_gateway_access_url": "http://10.66.66.1:32080/",
                "shell_embed_url": "http://10.66.66.1:32080/shell/",
                "workspace_status_url": "http://10.66.66.1:32080/api/workspace/status",
            },
            "wireguard_profile": {
                "server_public_key": "server-pub",
                "endpoint_host": "81.70.52.75",
                "endpoint_port": 51820,
                "client_address": "10.66.66.201/32",
                "allowed_ips": ["10.66.66.1/32"],
            },
        }
        runtime_session = {"id": "runtime-1", "status": "ready", "runtime_bundle_status": "running"}
        state.set_activation(order, grant, runtime_plan)
        state.set_runtime_session(
            runtime_session,
            runtime_plan=runtime_plan,
            wireguard_keypair={"private_key": "priv", "public_key": "pub"},
        )
        return settings, state

    def test_wireguard_up_requires_runtime_gateway_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings, state = self._seed_runtime_state(tmpdir)
            with (
                patch("buyer_client_app.session_ops.write_config"),
                patch(
                    "buyer_client_app.session_ops.bring_up",
                    return_value={"status": "up", "interface_name": "pivot-12345678", "config_path": "x"},
                ),
                patch("buyer_client_app.session_ops.bring_down") as bring_down,
                patch(
                    "buyer_client_app.session_ops.httpx.Client.get",
                    side_effect=Exception("should not be called directly"),
                ),
            ):
                with patch(
                    "buyer_client_app.session_ops._verify_runtime_gateway_readability",
                    return_value={"ok": False, "health_url": "http://10.66.66.1:32080/health", "exception": "timed out"},
                ):
                    with self.assertRaises(LocalAppError) as error:
                        wireguard_up(settings=settings, state=state)

        self.assertEqual(error.exception.code, "wireguard_gateway_unreachable")
        bring_down.assert_called_once()

    def test_wireguard_up_returns_gateway_probe_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings, state = self._seed_runtime_state(tmpdir)
            with (
                patch("buyer_client_app.session_ops.write_config"),
                patch(
                    "buyer_client_app.session_ops.bring_up",
                    return_value={"status": "up", "interface_name": "pivot-12345678", "config_path": "x"},
                ),
                patch(
                    "buyer_client_app.session_ops._verify_runtime_gateway_readability",
                    return_value={
                        "ok": True,
                        "health_url": "http://10.66.66.1:32080/health",
                        "status_code": 200,
                        "payload": {"status": "ok"},
                        "attempt": 1,
                    },
                ),
            ):
                result = wireguard_up(settings=settings, state=state)

        self.assertEqual(result["status"], "up")
        self.assertEqual(result["gateway_probe"]["status_code"], 200)
        self.assertEqual(result["gateway_probe"]["payload"]["status"], "ok")

    def test_create_runtime_session_waits_until_ready(self) -> None:
        class FakeBackendClient:
            def __init__(self) -> None:
                self.refresh_calls = 0

            def redeem_access_grant(self, grant_id: str, public_key: str, network_mode: str = "wireguard") -> dict:
                return {
                    "id": "runtime-1",
                    "access_grant_id": grant_id,
                    "order_id": "order-1",
                    "status": "allocating",
                    "runtime_bundle_status": "provisioning",
                }

            def get_runtime_session(self, runtime_session_id: str) -> dict:
                self.refresh_calls += 1
                if self.refresh_calls < 2:
                    return {
                        "id": runtime_session_id,
                        "access_grant_id": "grant-1",
                        "order_id": "order-1",
                        "status": "failed",
                        "runtime_bundle_status": "failed",
                    }
                return {
                    "id": runtime_session_id,
                    "access_grant_id": "grant-1",
                    "order_id": "order-1",
                    "status": "ready",
                    "runtime_bundle_status": "running",
                }

            def list_active_access_grants(self) -> dict:
                return {
                    "items": [
                        {
                            "id": "grant-1",
                            "order_id": "order-1",
                            "runtime_session_id": "runtime-1",
                            "status": "redeemed",
                        }
                    ],
                    "total": 1,
                }

            def get_order(self, order_id: str) -> dict:
                return {"id": order_id, "offer_id": "offer-1", "status": "session_active"}

        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(non_windows_workspace_root=tmpdir)
            state = BuyerClientState(settings)
            order = {"id": "order-1", "offer_id": "offer-1", "status": "grant_issued"}
            grant = {"id": "grant-1", "order_id": "order-1", "runtime_session_id": "runtime-1", "status": "redeemed"}
            runtime_plan = {"runtime_session_id": "runtime-1", "network_entry": {}, "wireguard_profile": {}}
            state.set_activation(order, grant, runtime_plan)
            backend_client = FakeBackendClient()
            with (
                patch("buyer_client_app.session_ops.generate_keypair", return_value=("priv", "pub")),
                patch("buyer_client_app.session_ops.time.sleep"),
            ):
                result = create_runtime_session(
                    settings=settings,
                    state=state,
                    backend_client=backend_client,
                    grant_id="grant-1",
                )

        self.assertEqual(result["runtime_session"]["status"], "ready")
        self.assertEqual(result["runtime_session"]["runtime_bundle_status"], "running")
        self.assertEqual(result["wireguard_public_key"], "pub")
        self.assertEqual(backend_client.refresh_calls, 2)


if __name__ == "__main__":
    unittest.main()
