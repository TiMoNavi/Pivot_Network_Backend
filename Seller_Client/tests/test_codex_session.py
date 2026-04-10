from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.codex_session import (
    CodexSessionError,
    _build_assistant_prompt,
    prepare_codex_session,
    run_codex_assistant,
)
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
        "expected_wireguard_ip": "10.0.8.12",
        "probe_summary": None,
        "container_runtime_probe": None,
        "last_join_complete": None,
        "manager_acceptance": {"status": "pending"},
    }


class FakeProcess:
    def __init__(self, command: list[str]) -> None:
        self.command = command
        self.returncode = 0
        output_path = Path(command[command.index("-o") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("assistant ok", encoding="utf-8")

    def communicate(self, timeout: int) -> tuple[str, str]:
        del timeout
        return ("stdout ok", "")


class FakeMcpFailureProcess(FakeProcess):
    def communicate(self, timeout: int) -> tuple[str, str]:
        del timeout
        return (
            "stdout ok",
            "mcp: seller-client-tools-session_x starting\nmcp startup: failed: seller-client-tools-session_x\n"
            "handshaking with MCP server failed\n",
        )


class CapturingProcess(FakeProcess):
    last_prompt: str = ""

    def __init__(self, command: list[str]) -> None:
        type(self).last_prompt = command[-1]
        super().__init__(command)


class CodexSessionTests(unittest.TestCase):
    def test_build_assistant_prompt_compacts_large_runtime_snapshot(self) -> None:
        snapshot = {
            "current_user": {"id": "user-1", "email": "seller@example.com"},
            "auth_session": {"expires_at": "2026-04-07T23:00:00Z"},
            "onboarding_session": {
                **sample_session_payload(),
                "status": "verified",
                "swarm_join_material": {
                    **dict(sample_session_payload()["swarm_join_material"]),
                    "manager_addr": "10.66.66.1",
                },
                "last_join_complete": {
                    "join_mode": "wireguard",
                    "path_outcome": "swarm_manager_verified",
                    "success_standard": "manager_task_execution",
                    "raw_payload": {"stdout": "x" * 50000},
                    "join_effect": {
                        "success_standard": "manager_task_execution",
                        "swarm_connectivity": {
                            "verified": True,
                            "local_node_state": "active",
                            "local_node_addr": "10.66.66.10",
                            "expected_remote_manager": "10.66.66.1:2377",
                        },
                        "manager_task_execution": {
                            "verified": True,
                            "proof_source": "existing_running_task",
                            "service_name": "portainer_agent",
                            "task_name": "portainer_agent.1",
                            "node_id": "worker-node-1",
                        },
                    },
                },
            },
            "last_runtime_workflow": {
                "kind": "execute_guided_join",
                "join_effect": {"success_standard": "manager_task_execution"},
                "payload": {"stdout": "y" * 50000},
            },
        }

        prompt = _build_assistant_prompt(snapshot, "帮我接入")

        self.assertIn('"manager_addr": "10.66.66.1"', prompt)
        self.assertIn('"success_standard": "manager_task_execution"', prompt)
        self.assertIn("Do not answer with a capabilities overview.", prompt)
        self.assertIn("call MCP tools before replying", prompt)
        self.assertNotIn("x" * 1000, prompt)
        self.assertNotIn("y" * 1000, prompt)
        self.assertLess(len(prompt), 12000)

    def test_prepare_and_run_assistant_use_session_scoped_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            config_template = tmpdir_path / "codex.config.toml"
            auth_file = tmpdir_path / "auth.json"
            config_template.write_text("model = 'gpt-5.4'\n", encoding="utf-8")
            auth_file.write_text('{"token":"secret"}\n', encoding="utf-8")

            settings = Settings(
                windows_workspace_root=str(tmpdir_path / "workspace"),
                non_windows_workspace_root=str(tmpdir_path / "workspace"),
                codex_config_template_path=config_template,
                codex_auth_source_path=auth_file,
            )
            runtime_state = SellerClientState(settings)
            runtime_state.set_auth(
                "token-1",
                {"id": "user-1", "email": "seller@example.com"},
                "2026-04-07T23:00:00Z",
            )
            runtime_state.set_onboarding(sample_session_payload())

            def fake_run(*args, **kwargs):
                del args, kwargs
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                patch("seller_client_app.codex_session.shutil.which", return_value="/usr/bin/codex"),
                patch("seller_client_app.codex_session._global_codex_config_path", return_value=tmpdir_path / "global-codex-config.toml"),
                patch("seller_client_app.codex_session.subprocess.run", side_effect=fake_run),
                patch(
                    "seller_client_app.codex_session.subprocess.Popen",
                    side_effect=lambda command, **kwargs: FakeProcess(command),
                ),
            ):
                paths = prepare_codex_session(settings=settings, state=runtime_state, session_id="join-session-0001")
                self.assertTrue((paths.codex_dotdir / "config.toml").exists())
                self.assertTrue((paths.codex_dotdir / "auth.json").exists())
                global_config = (tmpdir_path / "global-codex-config.toml").read_text(encoding="utf-8")
                self.assertIn("[mcp_servers.seller-client-tools]", global_config)
                self.assertIn("run-seller-fastmcp.py", global_config)

                result = run_codex_assistant(
                    settings=settings,
                    state=runtime_state,
                    session_id="join-session-0001",
                    user_message="read state",
                )
                self.assertEqual(result["assistant_message"], "assistant ok")
                self.assertEqual(result["assistant_mode"], "codex_mcp_stdio_global")
                self.assertIn("session_root", result)

    def test_run_codex_assistant_keeps_prompt_small_for_large_persisted_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            config_template = tmpdir_path / "codex.config.toml"
            auth_file = tmpdir_path / "auth.json"
            config_template.write_text("model = 'gpt-5.4'\n", encoding="utf-8")
            auth_file.write_text('{"token":"secret"}\n', encoding="utf-8")

            settings = Settings(
                windows_workspace_root=str(tmpdir_path / "workspace"),
                non_windows_workspace_root=str(tmpdir_path / "workspace"),
                codex_config_template_path=config_template,
                codex_auth_source_path=auth_file,
            )
            runtime_state = SellerClientState(settings)
            runtime_state.set_auth(
                "token-1",
                {"id": "user-1", "email": "seller@example.com"},
                "2026-04-07T23:00:00Z",
            )
            payload = sample_session_payload()
            payload["status"] = "verified"
            payload["swarm_join_material"]["manager_addr"] = "10.66.66.1"
            payload["last_join_complete"] = {
                "join_mode": "wireguard",
                "path_outcome": "swarm_manager_verified",
                "success_standard": "manager_task_execution",
                "raw_payload": {"stdout": "x" * 50000},
                "join_effect": {
                    "success_standard": "manager_task_execution",
                    "manager_task_execution": {
                        "verified": True,
                        "proof_source": "existing_running_task",
                    },
                },
            }
            runtime_state.set_onboarding(payload)
            runtime_state.record_runtime_workflow_result(
                {
                    "kind": "execute_guided_join",
                    "result": {
                        "join_effect": {
                            "success_standard": "manager_task_execution",
                            "manager_task_execution": {
                                "verified": True,
                                "proof_source": "existing_running_task",
                            },
                        }
                    },
                    "payload": {"stdout": "y" * 50000},
                }
            )

            def fake_run(*args, **kwargs):
                del args, kwargs
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                patch("seller_client_app.codex_session.shutil.which", return_value="/usr/bin/codex"),
                patch("seller_client_app.codex_session._global_codex_config_path", return_value=tmpdir_path / "global-codex-config.toml"),
                patch("seller_client_app.codex_session.subprocess.run", side_effect=fake_run),
                patch(
                    "seller_client_app.codex_session.subprocess.Popen",
                    side_effect=lambda command, **kwargs: CapturingProcess(command),
                ),
            ):
                prepare_codex_session(settings=settings, state=runtime_state, session_id="join-session-0001")
                result = run_codex_assistant(
                    settings=settings,
                    state=runtime_state,
                    session_id="join-session-0001",
                    user_message="帮我接入",
                )

            self.assertEqual(result["assistant_message"], "assistant ok")
            self.assertIn('"manager_addr": "10.66.66.1"', CapturingProcess.last_prompt)
            self.assertNotIn("x" * 1000, CapturingProcess.last_prompt)
            self.assertNotIn("y" * 1000, CapturingProcess.last_prompt)
            self.assertLess(len(CapturingProcess.last_prompt), 12000)

    def test_run_codex_assistant_raises_when_mcp_startup_failed_even_if_exit_code_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            config_template = tmpdir_path / "codex.config.toml"
            auth_file = tmpdir_path / "auth.json"
            config_template.write_text("model = 'gpt-5.4'\n", encoding="utf-8")
            auth_file.write_text('{"token":"secret"}\n', encoding="utf-8")

            settings = Settings(
                windows_workspace_root=str(tmpdir_path / "workspace"),
                non_windows_workspace_root=str(tmpdir_path / "workspace"),
                codex_config_template_path=config_template,
                codex_auth_source_path=auth_file,
            )
            runtime_state = SellerClientState(settings)
            runtime_state.set_auth(
                "token-1",
                {"id": "user-1", "email": "seller@example.com"},
                "2026-04-07T23:00:00Z",
            )
            runtime_state.set_onboarding(sample_session_payload())

            def fake_run(*args, **kwargs):
                del args, kwargs
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                patch("seller_client_app.codex_session.shutil.which", return_value="/usr/bin/codex"),
                patch("seller_client_app.codex_session._global_codex_config_path", return_value=tmpdir_path / "global-codex-config.toml"),
                patch("seller_client_app.codex_session.subprocess.run", side_effect=fake_run),
                patch(
                    "seller_client_app.codex_session.subprocess.Popen",
                    side_effect=lambda command, **kwargs: FakeMcpFailureProcess(command),
                ),
            ):
                prepare_codex_session(settings=settings, state=runtime_state, session_id="join-session-0001")
                with self.assertRaises(CodexSessionError):
                    run_codex_assistant(
                        settings=settings,
                        state=runtime_state,
                        session_id="join-session-0001",
                        user_message="read state",
                    )
