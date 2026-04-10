from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.flow import build_runtime_access_plan


class RuntimeFlowTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
