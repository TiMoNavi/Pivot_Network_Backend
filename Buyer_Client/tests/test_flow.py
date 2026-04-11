from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.flow import build_runtime_access_plan
from buyer_client_app.wireguard import build_interface_name


class RuntimeFlowTests(unittest.TestCase):
    def test_wireguard_interface_name_is_linux_safe(self) -> None:
        interface_name = build_interface_name(
            "pivot-buyer",
            "runtime_session_bd6eab1e6279291f",
        )

        self.assertLessEqual(len(interface_name), 15)
        self.assertNotIn("_", interface_name)
        self.assertTrue(interface_name.startswith("pivot-"))

    def test_effective_target_only_grant_is_pending_bundle(self) -> None:
        order = {
            "id": "order-1",
            "offer_id": "offer-medium-gpu",
            "status": "grant_issued",
        }
        grant = {
            "id": "grant-1",
            "runtime_session_id": "runtime-1",
            "status": "issued",
            "grant_type": "placeholder",
            "connect_material_payload": {
                "grant_mode": "effective_target_available",
                "effective_target_addr": "10.66.66.10",
                "effective_target_source": "backend_correction",
                "truth_authority": "backend_correction",
            },
        }

        plan = build_runtime_access_plan(order, grant)

        self.assertEqual(plan["status"], "pending_runtime_bundle")
        self.assertEqual(plan["purchase_semantics"], "runtime_bundle")
        self.assertEqual(plan["truth_lane"]["effective_target_addr"], "10.66.66.10")
        self.assertIn("wait_for_bundle_connect_metadata", plan["next_actions"])

    def test_gateway_connect_material_marks_plan_ready(self) -> None:
        order = {"id": "order-2", "offer_id": "offer-small-cpu"}
        grant = {
            "id": "grant-2",
            "runtime_session_id": "runtime-2",
            "status": "active",
            "grant_type": "runtime_bundle",
            "connect_material_payload": {
                "gateway_access_url": "https://81.70.52.75:32001/",
                "wireguard_gateway_access_url": "https://10.66.66.1:32001/",
                "shell_embed_url": "https://10.66.66.1:32001/shell/",
                "workspace_sync_url": "https://10.66.66.1:32001/api/workspace/upload",
                "runtime_service_name": "runtime-runtime-2",
                "gateway_service_name": "gateway-runtime-2",
                "network_name": "pivot-session-runtime-2",
                "server_public_key": "server-pub",
                "server_access_ip": "10.66.66.1",
                "client_address": "10.66.66.200/32",
            },
        }

        plan = build_runtime_access_plan(order, grant)

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["network_entry"]["mode"], "wireguard")
        self.assertEqual(plan["swarm_bundle"]["gateway_service_name"], "gateway-runtime-2")
        self.assertIn("open_runtime_shell", plan["next_actions"])

    def test_runtime_session_connect_metadata_derives_stage4_urls(self) -> None:
        order = {"id": "order-3", "offer_id": "offer-linux-runtime"}
        grant = {
            "id": "grant-3",
            "runtime_session_id": "runtime-3",
            "status": "redeemed",
            "grant_type": "runtime_bundle",
            "connect_material_payload": {},
        }
        runtime_session = {
            "id": "runtime-3",
            "status": "ready",
            "runtime_bundle_status": "running",
            "runtime_service_name": "runtime-runtime-3",
            "gateway_service_name": "gateway-runtime-3",
            "network_name": "pivot-session-runtime-3",
            "connect_metadata": {
                "wireguard_shell_embed_url": "http://10.66.66.1:32080/shell/runtime-3",
                "workspace_sync_url": "http://10.66.66.1:32080/api/workspace/upload/runtime-3",
            },
            "wireguard_lease_metadata": {
                "server_public_key": "server-pub",
                "server_access_ip": "10.66.66.1",
                "endpoint_host": "81.70.52.75",
                "endpoint_port": 51820,
                "client_address": "10.66.66.200",
                "client_allowed_ips": ["10.66.66.1/32"],
                "persistent_keepalive": 25,
            },
        }

        plan = build_runtime_access_plan(order, grant, runtime_session)

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["runtime_session_status"], "ready")
        self.assertEqual(
            plan["network_entry"]["workspace_extract_url"],
            "http://10.66.66.1:32080/api/workspace/extract",
        )
        self.assertEqual(
            plan["network_entry"]["task_exec_url"],
            "http://10.66.66.1:32080/api/exec",
        )
        self.assertEqual(plan["wireguard_profile"]["allowed_ips"], ["10.66.66.1/32"])
        self.assertIn("sync_workspace", plan["next_actions"])
        self.assertIn("submit_task_execution", plan["next_actions"])


if __name__ == "__main__":
    unittest.main()
