from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND_ROOT = ROOT.parent / "Plantform_Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from backend_app.schemas.seller_onboarding import JoinCompleteWrite
except ModuleNotFoundError:
    class JoinCompleteWrite(BaseModel):
        reported_phase: str
        node_ref: str | None = None
        compute_node_id: str | None = None
        observed_wireguard_ip: str | None = None
        observed_advertise_addr: str | None = None
        observed_data_path_addr: str | None = None
        notes: list[str] = Field(default_factory=list)
        raw_payload: dict[str, object] = Field(default_factory=dict)

from seller_client_app.bootstrap.backend_payloads import build_backend_write_payloads
from seller_client_app.bootstrap.phase1 import build_join_complete_payload, build_phase1_plan, build_probe_summary
from seller_client_app.contracts.phase1 import (
    BackendLocatorHint,
    BootstrapStage,
    JoinMaterialEnvelope,
    LocalJoinExecution,
    LocalJoinResult,
    PHASE1_ADAPTER_CAPABILITIES,
)


def sample_join_input() -> JoinMaterialEnvelope:
    return JoinMaterialEnvelope.from_dict(
        {
            "join_session_id": "join-session-0001",
            "seller_user_id": "seller-user-0001",
            "manager_addr": "10.66.66.1",
            "manager_port": 2377,
            "swarm_join_command": "docker swarm join --token SWMTKN-1-example 10.66.66.1:2377",
            "requested_offer_tier": "medium",
            "requested_accelerator": "gpu",
            "recommended_compute_node_id": "seller-user-0001-node-01",
            "expected_swarm_advertise_addr": "10.66.66.11",
            "expected_wireguard_ip": "10.66.66.11",
            "required_labels": {
                "platform.role": "compute",
                "platform.compute_enabled": "true",
                "platform.seller_user_id": "seller-user-0001",
                "platform.compute_node_id": "seller-user-0001-node-01",
                "platform.accelerator": "gpu",
            },
        }
    )


class Phase1ContractTests(unittest.TestCase):
    def test_phase1_plan_keeps_three_layers_four_stages_and_backend_only_adapter_boundary(self) -> None:
        plan = build_phase1_plan(sample_join_input())

        self.assertEqual([stage.stage.value for stage in plan.stage_plans], ["detect", "prepare", "install", "repair"])

        layers = {operation.layer.value for stage in plan.stage_plans for operation in stage.operations}
        self.assertEqual(layers, {"Linux Host", "Linux substrate", "Container Runtime"})
        self.assertEqual(plan.join_input.adapter_capabilities, PHASE1_ADAPTER_CAPABILITIES)

        boundaries = {boundary.component: boundary for boundary in plan.execution_boundaries}
        self.assertIn("call Adapter endpoints directly", boundaries["seller_client"].forbidden_actions)
        self.assertIn(
            "run inspect / claim / inspect acceptance flow",
            boundaries["backend.adapter_client"].responsibilities,
        )

        join_complete = plan.join_complete_template.to_dict()
        self.assertIn("local_execution", join_complete)
        self.assertIn("backend_locator", join_complete)
        self.assertIn("node_probe_summary", join_complete)
        self.assertNotIn("platform_acceptance", join_complete)

    def test_join_complete_keeps_runtime_write_shape_local_only(self) -> None:
        join_input = sample_join_input()
        probe_summary = build_probe_summary(join_input)
        payload = build_join_complete_payload(
            join_input,
            probe_summary,
            local_execution=LocalJoinExecution(
                join_command_executed=True,
                result=LocalJoinResult.SUCCEEDED,
                reported_phase=probe_summary.bootstrap_sequence[2],
                observed_wireguard_ip="10.66.66.11",
                observed_swarm_advertise_addr="10.66.66.11",
                swarm_node_id_hint="worker-node-id-001",
                detail="docker swarm join exited 0 locally",
            ),
            backend_locator=BackendLocatorHint(
                compute_node_id=join_input.recommended_compute_node_id,
                node_ref="node-1",
                hostname="seller-node-01",
                machine_id="machine-id-0001",
                observed_wireguard_ip="10.66.66.11",
                observed_swarm_advertise_addr="10.66.66.11",
                swarm_node_id_hint="worker-node-id-001",
                required_labels=dict(join_input.required_labels),
            ),
        ).to_dict()

        self.assertEqual(payload["local_execution"]["result"], "succeeded")
        self.assertEqual(payload["local_execution"]["reported_phase"], "install")
        self.assertEqual(payload["local_execution"]["observed_wireguard_ip"], "10.66.66.11")
        self.assertEqual(payload["backend_locator"]["compute_node_id"], "seller-user-0001-node-01")
        self.assertEqual(payload["backend_locator"]["node_ref"], "node-1")
        self.assertEqual(payload["backend_locator"]["hostname"], "seller-node-01")
        self.assertEqual(
            payload["backend_locator"]["required_labels"]["platform.compute_node_id"],
            "seller-user-0001-node-01",
        )
        self.assertEqual(payload["node_probe_summary"]["linux_host"]["reported_phase"], "detect")
        self.assertEqual(payload["node_probe_summary"]["linux_substrate"]["reported_phase"], "prepare")
        self.assertEqual(payload["node_probe_summary"]["container_runtime"]["reported_phase"], "install")
        self.assertNotIn("platform_acceptance", payload)

    def test_backend_write_payloads_flatten_runtime_local_contracts_for_backend_ingress(self) -> None:
        join_input = sample_join_input()
        probe_summary = build_probe_summary(join_input)
        probe_summary.linux_host.hostname = "seller-node-01"
        probe_summary.linux_host.kernel_release = "6.8.0"
        probe_summary.linux_host.cpu_cores = 16
        probe_summary.linux_host.memory_gb = 64
        probe_summary.linux_host.disk_free_gb = 512
        probe_summary.linux_host.observed_local_ips = ("192.168.1.10",)
        probe_summary.linux_substrate.docker_available = True
        probe_summary.linux_substrate.docker_version = "26.1"
        probe_summary.linux_substrate.wireguard_available = True
        probe_summary.linux_substrate.observed_local_ips = ("10.66.66.11",)
        probe_summary.linux_substrate.observed_wireguard_ip = "10.66.66.11"
        probe_summary.container_runtime.runtime_socket_access = True
        probe_summary.container_runtime.swarm_membership_state = "active"
        probe_summary.container_runtime.observed_swarm_advertise_addr = "10.66.66.11"
        probe_summary.container_runtime.swarm_node_id_hint = "worker-node-id-001"

        join_complete_payload = build_join_complete_payload(
            join_input,
            probe_summary,
            local_execution=LocalJoinExecution(
                join_command_executed=True,
                result=LocalJoinResult.SUCCEEDED,
                reported_phase=BootstrapStage.INSTALL,
                observed_wireguard_ip="10.66.66.11",
                observed_swarm_advertise_addr="10.66.66.11",
                swarm_node_id_hint="worker-node-id-001",
                detail="docker swarm join exited 0 locally",
            ),
            backend_locator=BackendLocatorHint(
                compute_node_id=join_input.recommended_compute_node_id,
                node_ref="node-1",
                hostname="seller-node-01",
                machine_id="machine-id-0001",
                observed_wireguard_ip="10.66.66.11",
                observed_swarm_advertise_addr="10.66.66.11",
                swarm_node_id_hint="worker-node-id-001",
                required_labels=dict(join_input.required_labels),
            ),
        )

        payloads = build_backend_write_payloads(probe_summary, join_complete_payload=join_complete_payload)

        self.assertEqual(payloads["linux_host_probe"]["reported_phase"], "detect")
        self.assertEqual(payloads["linux_host_probe"]["host_name"], "seller-node-01")

        substrate_payload = payloads["linux_substrate_probe"]
        self.assertEqual(substrate_payload["reported_phase"], "prepare")
        self.assertEqual(substrate_payload["cpu_cores"], 16)
        self.assertEqual(substrate_payload["memory_gb"], 64)
        self.assertEqual(substrate_payload["disk_free_gb"], 512)
        self.assertEqual(substrate_payload["observed_wireguard_ip"], "10.66.66.11")
        self.assertEqual(substrate_payload["observed_advertise_addr"], "10.66.66.11")
        self.assertIn("linux_host_capacity", substrate_payload["raw_payload"])

        runtime_payload = payloads["container_runtime_probe"]
        self.assertEqual(runtime_payload["reported_phase"], "install")
        self.assertTrue(runtime_payload["engine_available"])
        self.assertTrue(runtime_payload["network_ready"])

        join_complete = payloads["join_complete"]
        self.assertEqual(join_complete["reported_phase"], "install")
        self.assertEqual(join_complete["compute_node_id"], "seller-user-0001-node-01")
        self.assertEqual(join_complete["node_ref"], "node-1")
        self.assertEqual(join_complete["observed_wireguard_ip"], "10.66.66.11")
        self.assertEqual(join_complete["observed_advertise_addr"], "10.66.66.11")
        self.assertEqual(join_complete["notes"], ["docker swarm join exited 0 locally"])
        self.assertIn("backend_locator", join_complete["raw_payload"])
        self.assertIn("local_execution", join_complete["raw_payload"])
        self.assertNotIn("node_probe_summary", join_complete)
        self.assertNotIn("local_execution", join_complete)
        self.assertNotIn("backend_locator", join_complete)

        validated = JoinCompleteWrite(**join_complete)
        self.assertEqual(validated.reported_phase, "install")
        self.assertEqual(validated.compute_node_id, "seller-user-0001-node-01")
        self.assertEqual(validated.node_ref, "node-1")

    def test_probe_summary_exposes_rollback_checkpoints_for_backend_consumption(self) -> None:
        summary = build_probe_summary(sample_join_input()).to_dict()

        checkpoint_ids = {checkpoint["checkpoint_id"] for checkpoint in summary["rollback_checkpoints"]}
        self.assertEqual(
            checkpoint_ids,
            {
                "host.prepare-context",
                "substrate.prepare-network",
                "substrate.join-worker",
                "substrate.repair-network",
                "runtime.post-join-state",
            },
        )
        self.assertEqual(summary["linux_substrate"]["expected_wireguard_ip"], "10.66.66.11")
        self.assertEqual(summary["container_runtime"]["layer"], "Container Runtime")
        self.assertNotIn("manager_acceptance_owner", summary)
        self.assertNotIn("manager_acceptance_state", summary)
        self.assertEqual(summary["expected_wireguard_ip"], "10.66.66.11")

        stage_values = {
            point["stage"]
            for point in summary["linux_host"]["probe_points"]
            + summary["linux_substrate"]["probe_points"]
            + summary["container_runtime"]["probe_points"]
        }
        self.assertEqual(
            stage_values,
            {stage.value for stage in (BootstrapStage.DETECT, BootstrapStage.PREPARE, BootstrapStage.INSTALL, BootstrapStage.REPAIR)},
        )


if __name__ == "__main__":
    unittest.main()
