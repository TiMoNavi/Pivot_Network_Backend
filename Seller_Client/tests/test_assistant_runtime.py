from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.assistant_runtime import classify_assistant_intent, execute_assistant_request
from seller_client_app.codex_session import CodexSessionError
from seller_client_app.config import Settings
from seller_client_app.state import SellerClientState


def sample_session_payload() -> dict[str, object]:
    return {
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
        "expected_wireguard_ip": "10.66.66.10",
        "probe_summary": None,
        "container_runtime_probe": None,
        "last_join_complete": None,
        "manager_acceptance": {
            "status": "pending",
            "expected_wireguard_ip": "10.66.66.10",
            "observed_manager_node_addr": None,
            "matched": None,
            "detail": "not_checked",
        },
        "effective_target_addr": None,
        "effective_target_source": None,
        "truth_authority": "raw_manager",
        "minimum_tcp_validation": None,
    }


class AssistantRuntimeTests(unittest.TestCase):
    def test_classify_assistant_intent_detects_chinese_join_prompt(self) -> None:
        intent = classify_assistant_intent("帮我接入，并以 manager 那边可以正常执行 task 作为完成标准。")
        self.assertTrue(intent.prefers_codex)
        self.assertTrue(intent.wants_join_workflow)
        self.assertTrue(intent.wants_environment_check)
        self.assertTrue(intent.wants_overlay_check)
        self.assertTrue(intent.wants_refresh)
        self.assertTrue(intent.wants_state_summary)

    def test_classify_assistant_intent_detects_operational_join_prompt(self) -> None:
        intent = classify_assistant_intent("先检查环境，再执行 join workflow，最后刷新状态")
        self.assertTrue(intent.use_local_workflow)
        self.assertTrue(intent.prefers_codex)
        self.assertTrue(intent.wants_environment_check)
        self.assertTrue(intent.wants_overlay_check)
        self.assertTrue(intent.wants_join_workflow)
        self.assertTrue(intent.wants_refresh)

    def test_execute_assistant_request_routes_join_prompt_to_mcp_orchestration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=str(Path(tmpdir) / "workspace"))
            state = SellerClientState(settings)
            state.set_auth(
                "token-1",
                {"id": "user-1", "email": "seller@example.com"},
                "2026-04-07T23:00:00Z",
            )
            state.set_onboarding(sample_session_payload())

            with patch(
                "seller_client_app.assistant_runtime._execute_join_request_via_mcp",
                return_value={"assistant_message": "join via mcp ok", "assistant_mode": "mcp_orchestrated_join"},
            ) as run_join:
                result = execute_assistant_request(
                    settings=settings,
                    state=state,
                    session_id="join-session-0001",
                    user_message="帮我接入，并以 manager task execution 作为完成标准。",
                )

            run_join.assert_called_once()
            self.assertEqual(result["assistant_mode"], "mcp_orchestrated_join")
            self.assertEqual(result["assistant_message"], "join via mcp ok")

    def test_execute_assistant_request_uses_codex_for_non_operational_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=str(Path(tmpdir) / "workspace"))
            state = SellerClientState(settings)
            state.set_onboarding(sample_session_payload())

            with patch(
                "seller_client_app.assistant_runtime.run_codex_assistant",
                return_value={"assistant_message": "assistant ok", "assistant_mode": "codex_mcp"},
            ) as run_codex:
                result = execute_assistant_request(
                    settings=settings,
                    state=state,
                    session_id="join-session-0001",
                    user_message="帮我写一段卖家欢迎文案",
                )

            run_codex.assert_called_once()
            self.assertEqual(result["assistant_message"], "assistant ok")

    def test_execute_assistant_request_prefers_codex_when_prompt_explicitly_mentions_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=str(Path(tmpdir) / "workspace"))
            state = SellerClientState(settings)
            state.set_onboarding(sample_session_payload())

            with patch(
                "seller_client_app.assistant_runtime.run_codex_assistant",
                return_value={"assistant_message": "mcp ok", "assistant_mode": "codex_mcp"},
            ) as run_codex:
                result = execute_assistant_request(
                    settings=settings,
                    state=state,
                    session_id="join-session-0001",
                    user_message="请通过 Codex MCP 读取 onboarding state",
                )

            run_codex.assert_called_once()
            self.assertEqual(result["assistant_message"], "mcp ok")

    def test_execute_assistant_request_falls_back_to_local_summary_when_codex_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=str(Path(tmpdir) / "workspace"))
            state = SellerClientState(settings)
            state.set_onboarding(sample_session_payload())

            with patch(
                "seller_client_app.assistant_runtime.run_codex_assistant",
                side_effect=CodexSessionError("mcp timeout"),
            ):
                result = execute_assistant_request(
                    settings=settings,
                    state=state,
                    session_id="join-session-0001",
                    user_message="帮我写一段卖家欢迎文案",
                )

            self.assertEqual(result["assistant_mode"], "local_state_fallback")
            self.assertEqual(result["actions_run"][0]["action"], "read_state")

    def test_execute_assistant_request_falls_back_to_read_only_summary_when_codex_fails_for_join_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(windows_workspace_root=str(Path(tmpdir) / "workspace"))
            state = SellerClientState(settings)
            state.set_auth(
                "token-1",
                {"id": "user-1", "email": "seller@example.com"},
                "2026-04-07T23:00:00Z",
            )
            state.set_onboarding(sample_session_payload())

            with patch(
                "seller_client_app.assistant_runtime._execute_join_request_via_mcp",
                side_effect=RuntimeError("mcp orchestration failed"),
            ):
                result = execute_assistant_request(
                    settings=settings,
                    state=state,
                    session_id="join-session-0001",
                    user_message="帮我加入 swarm，然后总结状态",
                )

            self.assertEqual(result["assistant_mode"], "local_state_fallback")
            self.assertEqual(result["codex_error"], "mcp orchestration failed")
            self.assertEqual(result["actions_run"][0]["action"], "read_state")
            self.assertIn("no actual join, repair, or verification action was executed", result["assistant_message"])
            self.assertIsNone(state.current_last_runtime_workflow())
            self.assertIsNone(state.current_local_health_snapshot())


if __name__ == "__main__":
    unittest.main()
