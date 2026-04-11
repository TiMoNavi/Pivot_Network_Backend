from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.assistant_runtime import execute_assistant_request, extract_workspace_path
from buyer_client_app.config import Settings
from buyer_client_app.state import BuyerClientState


class AssistantRuntimeTests(unittest.TestCase):
    def test_extract_workspace_path_supports_windows_drive_paths(self) -> None:
        path = extract_workspace_path(
            r"使用当前 active grant 建立 runtime session，然后同步 D:\AI\Pivot_Client\buyer_client 并执行 `pwd`。"
        )

        self.assertEqual(path, r"D:\AI\Pivot_Client\buyer_client")

    def test_execute_assistant_request_runs_stage5_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(non_windows_workspace_root=tmpdir)
            state = BuyerClientState(settings)
            state.set_auth(
                "token-1",
                {
                    "id": "buyer-1",
                    "email": "buyer@example.com",
                    "display_name": "Buyer One",
                    "role": "buyer",
                },
                None,
            )

            order = {
                "id": "order-1",
                "offer_id": "offer-1",
                "status": "session_active",
            }
            grant = {
                "id": "grant-1",
                "order_id": "order-1",
                "runtime_session_id": "runtime-1",
                "status": "redeemed",
                "grant_type": "runtime_bundle",
                "connect_material_payload": {"grant_code": "grant-code-stage5-1234567890"},
            }
            runtime_plan = {
                "runtime_session_id": "runtime-1",
                "network_entry": {
                    "shell_embed_url": "http://10.66.66.1:32080/shell/",
                    "workspace_sync_url": "http://10.66.66.1:32080/api/workspace/upload",
                    "workspace_extract_url": "http://10.66.66.1:32080/api/workspace/extract",
                    "workspace_status_url": "http://10.66.66.1:32080/api/workspace/status",
                    "task_exec_url": "http://10.66.66.1:32080/api/exec",
                },
                "wireguard_profile": {
                    "server_public_key": "server-pub",
                    "endpoint_host": "81.70.52.75",
                    "endpoint_port": 51820,
                    "client_address": "10.66.66.200/32",
                    "allowed_ips": ["10.66.66.1/32"],
                },
            }
            runtime_session = {
                "id": "runtime-1",
                "status": "ready",
                "runtime_bundle_status": "running",
            }
            tool_calls: list[str] = []

            def fake_invoke_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
                tool_calls.append(name)
                if name == "read_runtime_state":
                    return state.runtime_snapshot()
                if name == "list_active_grants":
                    state.set_active_access_grants([grant])
                    return {"items": [grant], "total": 1}
                if name == "create_runtime_session":
                    state.set_activation(order, grant, runtime_plan)
                    state.set_runtime_session(
                        runtime_session,
                        runtime_plan=runtime_plan,
                        wireguard_keypair={"private_key": "priv", "public_key": "pub"},
                    )
                    return {"runtime_session": runtime_session, "runtime_access_plan": runtime_plan}
                if name == "wireguard_up":
                    state.set_wireguard_state({"status": "up", "interface_name": "pivot-12345678"})
                    return {"status": "up", "interface_name": "pivot-12345678"}
                if name == "open_shell":
                    return {"shell_embed_url": "http://10.66.66.1:32080/shell/"}
                if name == "sync_workspace":
                    path = str(arguments["path"])
                    state.set_workspace_selection({"path": path})
                    return {"workspace_selection": {"path": path}}
                if name == "submit_task_execution":
                    state.record_task_execution({"id": "task-1", "command": "pwd", "status": "succeeded"})
                    return {"id": "task-1", "status": "succeeded", "exit_code": 0}
                if name == "tail_task_logs":
                    return {"task_id": "task-1", "stdout_tail": "/workspace", "stderr_tail": ""}
                raise AssertionError(f"unexpected tool call: {name}")

            with patch("buyer_client_app.assistant_runtime._invoke_tool", side_effect=fake_invoke_tool):
                result = execute_assistant_request(
                    settings=settings,
                    state=state,
                    user_message="使用当前 active grant 建立 runtime session，拉起 WireGuard，打开 shell，同步 /tmp/demo，然后执行 `pwd` 并返回结果。",
                )

        self.assertTrue(result["ok"])
        self.assertIn("RuntimeSession: runtime-1 / ready / running", result["assistant_message"])
        self.assertIn("WireGuard: up", result["assistant_message"])
        self.assertIn("Task stdout tail", result["assistant_message"])
        self.assertEqual(
            tool_calls,
            [
                "read_runtime_state",
                "list_active_grants",
                "create_runtime_session",
                "wireguard_up",
                "open_shell",
                "sync_workspace",
                "submit_task_execution",
                "tail_task_logs",
                "read_runtime_state",
            ],
        )


if __name__ == "__main__":
    unittest.main()
