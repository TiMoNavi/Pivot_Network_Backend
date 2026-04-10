from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.config import Settings
from seller_client_app.local_system import (
    check_network_environment,
    list_script_capabilities,
    prepare_machine_wireguard_config,
    run_standard_join_workflow,
    verify_manager_task_execution,
)


def _session_payload(*, manager_addr: str | None) -> dict[str, object]:
    return {
        "onboarding_session": {
            "session_id": "join-session-0001",
            "expected_wireguard_ip": "10.66.66.10",
            "swarm_join_material": {
                "manager_addr": manager_addr,
                "manager_port": 2377,
                "join_token": "join-token-1",
            },
        }
    }


class LocalSystemTests(unittest.TestCase):
    def test_run_standard_join_workflow_prefers_session_manager_addr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(_session_payload(manager_addr="10.66.66.1")), encoding="utf-8")
            settings = Settings(
                windows_workspace_root=tmpdir,
                manager_wireguard_address="192.0.2.44",
                manager_public_address="81.70.52.75",
            )

            with (
                patch("seller_client_app.local_system.platform.system", return_value="Windows"),
                patch(
                    "seller_client_app.local_system.prepare_machine_wireguard_config",
                    return_value={"ok": True, "status": "already_prepared", "target_path": "D:/tmp/wg-seller.conf"},
                ),
                patch(
                    "seller_client_app.local_system._run_process",
                    return_value={
                        "ok": True,
                        "command": [],
                        "exit_code": 0,
                        "stdout": '{"status":"ok"}',
                        "stderr": "",
                        "combined": '{"status":"ok"}',
                    },
                ) as run_process,
            ):
                result = run_standard_join_workflow(settings, session_file=str(session_file))

        self.assertTrue(result["ok"])
        command = run_process.call_args.args[0]
        manager_addr_index = command.index("-ManagerWireGuardAddress") + 1
        self.assertEqual(command[manager_addr_index], "10.66.66.1")
        self.assertNotIn("-MinimumTcpValidationPort", command)
        self.assertEqual(result["wireguard_config_preparation"]["status"], "already_prepared")

    def test_run_standard_join_workflow_requires_session_manager_addr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(_session_payload(manager_addr=None)), encoding="utf-8")
            settings = Settings(windows_workspace_root=tmpdir)

            with patch("seller_client_app.local_system.platform.system", return_value="Windows"):
                result = run_standard_join_workflow(settings, session_file=str(session_file))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "session_manager_addr_missing")

    def test_prepare_machine_wireguard_config_copies_valid_source_into_cache(self) -> None:
        valid_config = (
            "[Interface]\n"
            "Address = 10.66.66.10/32\n"
            "PrivateKey = test-private-key\n"
            "\n"
            "[Peer]\n"
            "PublicKey = test-peer-key\n"
            "AllowedIPs = 10.66.66.1/32\n"
            "Endpoint = 81.70.52.75:45182\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "machine-wg.conf"
            cache_path = tmpdir_path / ".cache" / "seller-zero-flow" / "wireguard" / "wg-seller.conf"
            source_path.write_text(valid_config, encoding="utf-8")
            settings = Settings(windows_workspace_root=tmpdir)

            with patch.object(
                Settings,
                "wireguard_runtime_config_path",
                new_callable=PropertyMock,
                return_value=cache_path,
            ):
                result = prepare_machine_wireguard_config(
                    settings,
                    source_path=str(source_path),
                    expected_wireguard_ip="10.66.66.10",
                )

                self.assertTrue(result["ok"])
                self.assertEqual(result["status"], "prepared")
                self.assertEqual(result["target_path"], str(cache_path))
                self.assertTrue(cache_path.exists())
                self.assertEqual(cache_path.read_text(encoding="utf-8"), valid_config)

    def test_run_standard_join_workflow_fails_when_machine_wireguard_config_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(_session_payload(manager_addr="10.66.66.1")), encoding="utf-8")
            settings = Settings(windows_workspace_root=tmpdir)

            with (
                patch("seller_client_app.local_system.platform.system", return_value="Windows"),
                patch(
                    "seller_client_app.local_system.prepare_machine_wireguard_config",
                    return_value={"ok": False, "error": "machine_wireguard_config_missing", "status": "missing_machine_wireguard_config"},
                ),
            ):
                result = run_standard_join_workflow(settings, session_file=str(session_file))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "machine_wireguard_config_missing")
        self.assertEqual(result["wireguard_config_preparation"]["status"], "missing_machine_wireguard_config")

    def test_verify_manager_task_execution_invokes_probe_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(_session_payload(manager_addr="10.66.66.1")), encoding="utf-8")
            settings = Settings(windows_workspace_root=tmpdir, manager_public_address="81.70.52.75")

            with (
                patch("seller_client_app.local_system.platform.system", return_value="Windows"),
                patch(
                    "seller_client_app.local_system._run_process",
                    return_value={
                        "ok": True,
                        "command": [],
                        "exit_code": 0,
                        "stdout": '{"task_execution_verified": true, "status": "verified"}',
                        "stderr": "",
                        "combined": '{"task_execution_verified": true, "status": "verified"}',
                    },
                ) as run_process,
            ):
                result = verify_manager_task_execution(settings, session_file=str(session_file), task_probe_timeout_seconds=45)

        self.assertTrue(result["ok"])
        command = run_process.call_args.args[0]
        self.assertIn("probe_swarm_manager_task_execution.ps1", command[5])
        self.assertIn("-TaskProbeTimeoutSeconds", command)
        timeout_index = command.index("-TaskProbeTimeoutSeconds") + 1
        self.assertEqual(command[timeout_index], "45")

    def test_check_network_environment_uses_swarm_connectivity_as_success_standard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            session_file.write_text(json.dumps(_session_payload(manager_addr="10.66.66.1")), encoding="utf-8")
            settings = Settings(windows_workspace_root=tmpdir)
            health_payload = {
                "summary": {"status": "healthy", "warnings": []},
                "docker": {
                    "local_node_state": "active",
                    "node_addr": "10.66.66.10",
                    "swarm": {
                        "RemoteManagers": [
                            {"Addr": "10.66.66.1:2377"},
                        ]
                    },
                },
                "wireguard": {
                    "manager_port_checks": [{"port": 2377, "reachable": True}],
                    "route_summary": ["10.66.66.1 dev wg-seller"],
                },
            }

            with patch("seller_client_app.local_system.collect_environment_health", return_value=health_payload):
                result = check_network_environment(settings, session_file=str(session_file))

        self.assertEqual(result["success_standard"], "docker_swarm_connectivity")
        self.assertTrue(result["swarm_connectivity"]["verified"])
        self.assertEqual(result["swarm_connectivity"]["expected_remote_manager"], "10.66.66.1:2377")

    def test_list_script_capabilities_exposes_canonical_names_and_internal_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=tmpdir)
            result = list_script_capabilities(settings)

        capability_names = {item["tool_name"] for item in result["capabilities"]}
        self.assertIn("list_script_capabilities", result["recommended_join_sequence"])
        self.assertIn("prepare_machine_wireguard", capability_names)
        self.assertIn("execute_guided_join", capability_names)
        self.assertIn("verify_manager_task", capability_names)

        guided_join = next(item for item in result["capabilities"] if item["tool_name"] == "execute_guided_join")
        self.assertIn("run_guided_join_assessment", guided_join["legacy_tool_names"])
        self.assertTrue(any(script["relative_path"].endswith("probe_swarm_manager_task_execution.ps1") for script in guided_join["backing_scripts"]))

        internal_paths = {item["relative_path"] for item in result["internal_scripts"]}
        self.assertIn("bootstrap/windows/swarm_runtime_common.ps1", internal_paths)


if __name__ == "__main__":
    unittest.main()
