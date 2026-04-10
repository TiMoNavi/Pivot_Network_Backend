from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.config import Settings
from seller_client_app.mcp_http import (
    build_mcp_http_delete_response,
    build_mcp_http_get_response,
    build_mcp_http_post_response,
    ensure_http_mcp_bearer_token,
)


def sample_session_payload() -> dict[str, object]:
    return {
        "backend_base_url": "https://pivotcompute.store",
        "backend_api_prefix": "/api/v1",
        "auth_token": "token-1",
        "current_user": {"id": "user-1", "email": "seller@example.com"},
        "window_session": {"session_id": "window-1"},
        "last_assistant_run": None,
        "onboarding_session": {
            "session_id": "join-session-http",
            "seller_user_id": "seller-user-0001",
            "status": "issued",
            "requested_offer_tier": "medium",
            "requested_accelerator": "gpu",
            "requested_compute_node_id": "compute-seller-1",
            "swarm_join_material": {
                "manager_addr": "10.66.66.1",
                "manager_port": 2377,
                "swarm_join_command": "docker swarm join --token join-token-1 10.66.66.1:2377",
            },
            "required_labels": {"platform.role": "compute"},
            "expected_wireguard_ip": "10.0.8.12",
            "effective_target_addr": "10.0.8.12",
            "effective_target_source": "backend_correction",
            "truth_authority": "backend_correction",
            "minimum_tcp_validation": {
                "target_addr": "10.0.8.12",
                "target_port": 8080,
                "reachable": False,
            },
            "manager_acceptance": {"status": "pending"},
        },
        "runtime_evidence": {"correction_history": [], "tcp_validations": []},
        "local_health_snapshot": None,
        "last_runtime_workflow": None,
    }


class McpHttpTests(unittest.TestCase):
    def test_initialize_and_tools_list_over_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=tmpdir)
            session_id = "join-session-http"
            session_root = Path(tmpdir) / settings.session_subdir_name / session_id
            session_root.mkdir(parents=True, exist_ok=True)
            (session_root / "session.json").write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            token = ensure_http_mcp_bearer_token(settings, session_id)
            headers = {
                "Authorization": f"Bearer {token}",
                "MCP-Protocol-Version": "2024-11-05",
            }

            initialize = build_mcp_http_post_response(
                settings=settings,
                session_id=session_id,
                headers=headers,
                body=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(initialize.status_code, 200)
            self.assertEqual(initialize.body["result"]["protocolVersion"], "2024-11-05")

            tools_list = build_mcp_http_post_response(
                settings=settings,
                session_id=session_id,
                headers=headers,
                body=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                        "params": {},
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(tools_list.status_code, 200)
            tool_names = {tool["name"] for tool in tools_list.body["result"]["tools"]}
            self.assertIn("list_script_capabilities", tool_names)
            self.assertIn("execute_join_workflow", tool_names)
            self.assertIn("inspect_network_path", tool_names)
            self.assertIn("prepare_machine_wireguard", tool_names)
            self.assertIn("inspect_environment_health", tool_names)
            self.assertIn("verify_manager_task", tool_names)
            self.assertIn("start_local_service", tool_names)
            self.assertIn("cleanup_join_state", tool_names)

    def test_http_tools_call_requires_bearer_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=tmpdir)
            session_id = "join-session-http"
            session_root = Path(tmpdir) / settings.session_subdir_name / session_id
            session_root.mkdir(parents=True, exist_ok=True)
            (session_root / "session.json").write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            ensure_http_mcp_bearer_token(settings, session_id)

            response = build_mcp_http_post_response(
                settings=settings,
                session_id=session_id,
                headers={},
                body=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/list",
                        "params": {},
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(response.status_code, 401)

    def test_http_get_opens_sse_stream_and_delete_returns_405(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=tmpdir)
            session_id = "join-session-http"
            session_root = Path(tmpdir) / settings.session_subdir_name / session_id
            session_root.mkdir(parents=True, exist_ok=True)
            (session_root / "session.json").write_text(json.dumps(sample_session_payload()), encoding="utf-8")
            token = ensure_http_mcp_bearer_token(settings, session_id)
            headers = {"Authorization": f"Bearer {token}"}

            get_response = build_mcp_http_get_response(settings=settings, session_id=session_id, headers=headers)
            delete_response = build_mcp_http_delete_response(settings=settings, session_id=session_id, headers=headers)

            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.media_type, "text/event-stream")
            self.assertIn("id: 0", str(get_response.body))
            self.assertEqual(delete_response.status_code, 405)


if __name__ == "__main__":
    unittest.main()
