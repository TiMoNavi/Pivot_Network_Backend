from __future__ import annotations

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.mcp_server import _invoke_tool, _load_session_context, _tool_descriptors


def sample_session_payload() -> dict[str, object]:
    return {
        "backend_base_url": "https://pivotcompute.store",
        "backend_api_prefix": "/api/v1",
        "auth_token": "token-1",
        "current_user": {"id": "user-1", "email": "seller@example.com"},
        "window_session": {"session_id": "window-1"},
        "last_assistant_run": None,
        "onboarding_session": {
            "session_id": "join-session-0001",
            "seller_user_id": "seller-user-0001",
            "status": "issued",
            "requested_offer_tier": "medium",
            "requested_accelerator": "gpu",
            "requested_compute_node_id": "compute-seller-1",
            "swarm_join_material": {
                "manager_addr": "10.66.66.1",
                "manager_port": 2377,
                "swarm_join_command": "docker swarm join --token join-token-1 10.66.66.1:2377",
                "recommended_compute_node_id": "compute-seller-1",
                "registry_host": "registry.example.com",
                "registry_port": 5000,
                "recommended_labels": {
                    "platform.role": "compute",
                    "platform.compute_node_id": "compute-seller-1",
                    "platform.seller_user_id": "seller-user-0001",
                },
            },
            "required_labels": {
                "platform.role": "compute",
                "platform.compute_node_id": "compute-seller-1",
                "platform.seller_user_id": "seller-user-0001",
            },
            "expected_wireguard_ip": "10.0.8.12",
            "probe_summary": None,
            "container_runtime_probe": None,
            "last_join_complete": None,
            "effective_target_addr": "10.0.8.12",
            "effective_target_source": "backend_correction",
            "truth_authority": "backend_correction",
            "minimum_tcp_validation": {
                "target_addr": "10.0.8.12",
                "target_port": 8080,
                "reachable": False,
                "validated_against_effective_target": True,
            },
            "manager_acceptance": {"status": "pending"},
        },
        "local_health_snapshot": {
            "summary": {"status": "needs_attention", "warnings": ["docker"]},
            "docker": {"local_node_state": "inactive"},
        },
        "last_runtime_workflow": None,
    }


class FakeBackend:
    def __init__(self) -> None:
        self.updated_payload = {
            **sample_session_payload()["onboarding_session"],
            "status": "verified",
            "last_join_complete": {"compute_node_id": "compute-seller-1"},
        }

    def get_onboarding_session(self, session_id: str) -> dict[str, object]:
        assert session_id == "join-session-0001"
        return dict(self.updated_payload)

    def submit_join_complete(self, session_id: str, payload: dict[str, object]) -> dict[str, object]:
        assert session_id == "join-session-0001"
        assert payload["compute_node_id"] == "compute-seller-1"
        return dict(self.updated_payload)

    def close_onboarding_session(self, session_id: str) -> dict[str, object]:
        assert session_id == "join-session-0001"
        updated = dict(self.updated_payload)
        updated["status"] = "closed"
        return updated


class McpServerTests(unittest.TestCase):
    def test_tool_descriptors_only_expose_controlled_actions(self) -> None:
        names = {tool["name"] for tool in _tool_descriptors()}

        self.assertIn("list_script_capabilities", names)
        self.assertIn("read_environment_health", names)
        self.assertIn("inspect_environment_health", names)
        self.assertIn("repair_environment_health", names)
        self.assertIn("inspect_overlay_runtime", names)
        self.assertIn("inspect_network_path", names)
        self.assertIn("prepare_machine_wireguard", names)
        self.assertIn("execute_join_workflow", names)
        self.assertIn("execute_guided_join", names)
        self.assertIn("verify_manager_task", names)
        self.assertIn("start_local_service", names)
        self.assertIn("verify_local_service_content", names)
        self.assertIn("cleanup_join_state", names)
        self.assertIn("stop_local_service_and_cleanup", names)
        self.assertIn("export_diagnostics_bundle", names)
        self.assertIn("read_onboarding_state", names)
        self.assertIn("refresh_onboarding_session", names)
        self.assertIn("generate_phase1_probe_drafts", names)
        self.assertIn("submit_linux_host_probe", names)
        self.assertIn("submit_join_complete", names)
        self.assertIn("record_runtime_correction", names)
        self.assertIn("run_minimum_tcp_validation", names)
        self.assertNotIn("shell", names)
        self.assertNotIn("run_command", names)

    def test_generate_drafts_and_submit_join_complete_persist_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            payload = _load_session_context(str(session_file))
            backend = FakeBackend()

            with patch("seller_client_app.mcp_server._backend_client", return_value=backend):
                drafts = _invoke_tool("generate_phase1_probe_drafts", {}, payload, str(session_file))
                self.assertIn("write_payloads", drafts)
                self.assertIn("join_complete", drafts["write_payloads"])

                result = _invoke_tool(
                    "submit_join_complete",
                    {"compute_node_id": "compute-seller-1"},
                    payload,
                    str(session_file),
                )
                self.assertEqual(result["status"], "verified")

            persisted = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(persisted["onboarding_session"]["status"], "verified")
            self.assertEqual(
                persisted["onboarding_session"]["last_join_complete"]["compute_node_id"],
                "compute-seller-1",
            )

    def test_list_script_capabilities_returns_canonical_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            payload = _load_session_context(str(session_file))

            result = _invoke_tool("list_script_capabilities", {}, payload, str(session_file))

        capability_names = {item["tool_name"] for item in result["capabilities"]}
        self.assertIn("prepare_machine_wireguard", capability_names)
        self.assertIn("execute_guided_join", capability_names)
        self.assertIn("verify_manager_task", capability_names)
        self.assertIn("bootstrap/windows/clear_windows_join_state.ps1", {item["relative_path"] for item in result["internal_scripts"]})

    def test_read_state_and_join_material_expose_effective_target_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            payload = _load_session_context(str(session_file))

            state_view = _invoke_tool("read_onboarding_state", {}, payload, str(session_file))
            onboarding = state_view["onboarding_session"]
            self.assertEqual(onboarding["effective_target_addr"], "10.0.8.12")
            self.assertEqual(onboarding["effective_target_source"], "backend_correction")
            self.assertEqual(onboarding["truth_authority"], "backend_correction")
            self.assertFalse(onboarding["minimum_tcp_validation"]["reachable"])

            join_material = _invoke_tool("read_join_material", {}, payload, str(session_file))
            self.assertEqual(join_material["effective_target_addr"], "10.0.8.12")
            self.assertEqual(join_material["effective_target_source"], "backend_correction")
            self.assertEqual(join_material["truth_authority"], "backend_correction")
            self.assertFalse(join_material["minimum_tcp_validation"]["reachable"])

    def test_record_runtime_correction_and_tcp_validation_persist_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            payload = _load_session_context(str(session_file))

            correction = _invoke_tool(
                "record_runtime_correction",
                {
                    "correction_kind": "advertise_override",
                    "outcome": "succeeded",
                    "reported_phase": "repair",
                    "script_path": "Seller_Client/scripts/rejoin-windows-swarm.sh",
                    "notes": ["recorded locally only"],
                },
                payload,
                str(session_file),
            )
            self.assertEqual(correction["correction"]["correction_kind"], "advertise_override")
            self.assertEqual(correction["runtime_evidence"]["latest_correction"]["outcome"], "succeeded")

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                host, port = listener.getsockname()
                validation = _invoke_tool(
                    "run_minimum_tcp_validation",
                    {
                        "host": host,
                        "port": port,
                        "target_label": "corrected_seller_target",
                    },
                    payload,
                    str(session_file),
                )

            self.assertTrue(validation["validation"]["reachable"])
            persisted = json.loads(session_file.read_text(encoding="utf-8"))
            runtime_evidence = persisted["runtime_evidence"]
            self.assertEqual(len(runtime_evidence["correction_history"]), 1)
            self.assertEqual(len(runtime_evidence["tcp_validations"]), 1)
            self.assertEqual(runtime_evidence["latest_correction"]["correction_kind"], "advertise_override")
            self.assertTrue(runtime_evidence["latest_tcp_validation"]["reachable"])

    def test_environment_and_join_workflow_tools_persist_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            payload = _load_session_context(str(session_file))
            backend = FakeBackend()

            with (
                patch("seller_client_app.mcp_server._backend_client", return_value=backend),
                patch(
                    "seller_client_app.mcp_server.collect_environment_health",
                    return_value={"summary": {"status": "healthy", "warnings": []}, "docker": {"local_node_state": "active"}},
                ),
                patch(
                    "seller_client_app.mcp_server.run_standard_join_workflow",
                    return_value={
                        "ok": True,
                        "payload": {
                            "summary": {
                                "success_standard": "docker_swarm_connectivity",
                                "path_outcome": "swarm_manager_verified",
                                "swarm_connectivity_verified": True,
                            }
                        },
                    },
                ),
                patch(
                    "seller_client_app.mcp_server.run_overlay_runtime_check",
                    return_value={"ok": True, "payload": {"windows_overlay": {"manager_port_checks": []}}},
                ),
                patch(
                    "seller_client_app.mcp_server.export_diagnostics_bundle",
                    return_value={"bundle_path": "D:/tmp/diag.zip", "exists": True},
                ),
            ):
                env_result = _invoke_tool("inspect_environment_health", {}, payload, str(session_file))
                self.assertEqual(env_result["local_health_snapshot"]["summary"]["status"], "healthy")

                overlay_result = _invoke_tool("inspect_overlay_runtime", {}, payload, str(session_file))
                self.assertEqual(overlay_result["kind"], "overlay_runtime_check")

                workflow_result = _invoke_tool("execute_join_workflow", {}, payload, str(session_file))
                self.assertTrue(workflow_result["last_runtime_workflow"]["result"]["ok"])
                self.assertEqual(workflow_result["onboarding_session"]["status"], "verified")

                export_result = _invoke_tool("export_diagnostics_bundle", {}, payload, str(session_file))
                self.assertTrue(export_result["exists"])

            persisted = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(persisted["local_health_snapshot"]["summary"]["status"], "healthy")
            self.assertEqual(persisted["last_runtime_workflow"]["kind"], "execute_join_workflow")

    def test_network_and_local_service_tools_persist_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            payload = _load_session_context(str(session_file))

            with (
                patch(
                    "seller_client_app.mcp_server.check_network_environment",
                    return_value={
                        "success_standard": "docker_swarm_connectivity",
                        "swarm_connectivity": {"verified": True, "expected_remote_manager": "10.66.66.1:2377"},
                        "environment": {"summary": {"status": "healthy", "warnings": []}},
                    },
                ),
                patch(
                    "seller_client_app.mcp_server.prepare_machine_wireguard_config",
                    return_value={"ok": True, "status": "prepared", "target_path": "D:/tmp/wg-seller.conf"},
                ),
                patch(
                    "seller_client_app.mcp_server.start_local_service",
                    return_value={"ok": True, "status": "started", "port": 8901},
                ),
                patch(
                    "seller_client_app.mcp_server.retest_local_content",
                    return_value={"ok": True, "port": 8901, "results": [{"path": "/", "status_code": 200}]},
                ),
                patch(
                    "seller_client_app.mcp_server.stop_local_service",
                    return_value={"ok": True, "status": "stopped", "port": 8901},
                ),
                patch(
                    "seller_client_app.mcp_server.perform_clear_join_state",
                    return_value={"ok": True, "status": "cleared", "payload": {"after_state": {"local_node_state": "inactive"}}},
                ),
            ):
                network_result = _invoke_tool("inspect_network_path", {}, payload, str(session_file))
                self.assertTrue(network_result["swarm_connectivity"]["verified"])

                prep_result = _invoke_tool("prepare_machine_wireguard", {}, payload, str(session_file))
                self.assertEqual(prep_result["status"], "prepared")

                start_result = _invoke_tool("start_local_service", {}, payload, str(session_file))
                self.assertEqual(start_result["status"], "started")

                retest_result = _invoke_tool("verify_local_service_content", {}, payload, str(session_file))
                self.assertTrue(retest_result["ok"])

                stop_result = _invoke_tool(
                    "stop_local_service_and_cleanup",
                    {"dry_run": True, "refresh_onboarding_session": False},
                    payload,
                    str(session_file),
                )
                self.assertEqual(stop_result["local_service_stop"]["status"], "stopped")
                self.assertEqual(stop_result["clear_join_state"]["status"], "cleared")

            persisted = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(persisted["last_runtime_workflow"]["kind"], "stop_local_service_and_cleanup")

    def test_guided_join_assessment_runs_full_join_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            payload = _load_session_context(str(session_file))
            backend = FakeBackend()

            with (
                patch("seller_client_app.mcp_server._backend_client", return_value=backend),
                patch(
                    "seller_client_app.mcp_server.prepare_machine_wireguard_config",
                    return_value={"ok": True, "status": "prepared", "target_path": "D:/tmp/wg-seller.conf"},
                ),
                patch(
                    "seller_client_app.mcp_server.collect_environment_health",
                    return_value={
                        "summary": {"status": "healthy", "warnings": []},
                        "docker": {"local_node_state": "active", "node_addr": "10.0.8.12"},
                        "wireguard": {"interface_present": True},
                        "backend_connectivity": {"backend_ok": True},
                    },
                ),
                patch(
                    "seller_client_app.mcp_server.run_overlay_runtime_check",
                    return_value={"ok": True, "payload": {"windows_overlay": {"manager_routes": ["10.66.66.1 dev wg-seller"]}}},
                ),
                patch(
                    "seller_client_app.mcp_server.run_standard_join_workflow",
                    return_value={
                        "ok": True,
                        "payload": {
                            "summary": {
                                "success_standard": "docker_swarm_connectivity",
                                "path_outcome": "swarm_manager_verified",
                                "swarm_connectivity_verified": True,
                                "local_swarm_active": True,
                                "manager_acceptance_matched": True,
                            },
                            "join_result": {
                                "after_state": '{"LocalNodeState":"active","NodeID":"node-1","NodeAddr":"10.0.8.12"}',
                                "join_idempotent_reason": "already part of a swarm",
                            },
                        },
                    },
                ),
                patch(
                    "seller_client_app.mcp_server.verify_manager_task_execution",
                    return_value={
                        "ok": True,
                        "payload": {
                            "task_execution_verified": True,
                            "status": "verified",
                            "proof_source": "existing_running_task",
                            "selected_candidate": {"id": "node-1"},
                        },
                    },
                ),
            ):
                result = _invoke_tool("execute_guided_join", {}, payload, str(session_file))

            self.assertEqual(result["wireguard_config_preparation"]["status"], "prepared")
            self.assertEqual(result["environment"]["summary"]["status"], "healthy")
            self.assertEqual(result["join_material"]["expected_wireguard_ip"], "10.0.8.12")
            self.assertTrue(result["overlay_runtime"]["ok"])
            self.assertTrue(result["join_workflow"]["ok"])
            self.assertTrue(result["manager_task_execution"]["ok"])
            self.assertEqual(result["join_effect"]["local_join"]["local_node_addr"], "10.0.8.12")
            self.assertEqual(result["join_effect"]["backend_authoritative_target"]["session_status"], "verified")
            self.assertEqual(result["join_effect"]["success_standard"], "manager_task_execution")
            self.assertTrue(result["join_effect"]["swarm_connectivity"]["verified"])
            self.assertTrue(result["join_effect"]["manager_task_execution"]["verified"])

            persisted = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(persisted["last_runtime_workflow"]["kind"], "execute_guided_join")
            self.assertEqual(
                persisted["last_runtime_workflow"]["manager_task_execution"]["payload"]["proof_source"],
                "existing_running_task",
            )

    def test_clear_join_state_resets_runtime_evidence_and_refreshes_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            seeded_payload = sample_session_payload()
            seeded_payload["runtime_evidence"] = {
                "correction_history": [{"correction_kind": "advertise_override", "outcome": "succeeded"}],
                "latest_correction": {"correction_kind": "advertise_override", "outcome": "succeeded"},
                "tcp_validations": [{"host": "10.0.8.12", "port": 8080, "reachable": False}],
                "latest_tcp_validation": {"host": "10.0.8.12", "port": 8080, "reachable": False},
                "updated_at": "2026-04-09T12:00:00Z",
            }
            session_file.write_text(json.dumps(seeded_payload), encoding="utf-8")
            payload = _load_session_context(str(session_file))
            backend = FakeBackend()

            with (
                patch("seller_client_app.mcp_server._backend_client", return_value=backend),
                patch(
                    "seller_client_app.mcp_server.perform_clear_join_state",
                    return_value={"ok": True, "status": "dry_run", "payload": {"after_state": {"local_node_state": "inactive"}}},
                ),
                patch(
                    "seller_client_app.mcp_server.collect_environment_health",
                    return_value={"summary": {"status": "healthy", "warnings": []}, "docker": {"local_node_state": "inactive"}},
                ),
            ):
                result = _invoke_tool("cleanup_join_state", {"dry_run": True}, payload, str(session_file))

            self.assertEqual(result["clear_join_state"]["status"], "dry_run")
            self.assertEqual(result["onboarding_session"]["status"], "verified")
            self.assertEqual(result["runtime_evidence"]["correction_history"], [])
            self.assertEqual(result["last_runtime_workflow"]["kind"], "cleanup_join_state")

            persisted = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(persisted["runtime_evidence"]["tcp_validations"], [])
            self.assertEqual(persisted["last_runtime_workflow"]["kind"], "cleanup_join_state")
