from __future__ import annotations

import socket
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.main import app, state


def sample_session_payload(*, session_id: str = "join-session-0001", status: str = "issued") -> dict[str, object]:
    return {
        "session_id": session_id,
        "seller_user_id": "seller-user-0001",
        "status": status,
        "requested_offer_tier": "medium",
        "requested_accelerator": "gpu",
        "requested_compute_node_id": "compute-seller-1",
        "swarm_join_material": {
            "join_token": "join-token-1",
            "manager_addr": "10.66.66.1",
            "manager_port": 2377,
            "registry_host": "registry.example.com",
            "registry_port": 5000,
            "swarm_join_command": "docker swarm join --token join-token-1 10.66.66.1:2377",
            "claim_required": True,
            "recommended_compute_node_id": "compute-seller-1",
            "expected_wireguard_ip": "10.66.66.10",
            "recommended_labels": {
                "platform.role": "compute",
                "platform.compute_enabled": "true",
                "platform.compute_node_id": "compute-seller-1",
                "platform.seller_user_id": "seller-user-0001",
                "platform.accelerator": "gpu",
            },
            "next_step": "seller_host_runs_join_then_backend_calls_claim",
        },
        "required_labels": {
            "platform.role": "compute",
            "platform.compute_enabled": "true",
            "platform.compute_node_id": "compute-seller-1",
            "platform.seller_user_id": "seller-user-0001",
            "platform.accelerator": "gpu",
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
            "node_ref": None,
            "compute_node_id": "compute-seller-1",
            "checked_at": None,
            "detail": "awaiting_join_complete",
        },
        "expires_at": "2026-04-07T16:00:00Z",
        "last_heartbeat_at": None,
        "created_at": "2026-04-07T15:00:00Z",
        "updated_at": "2026-04-07T15:00:00Z",
    }


class Phase2AppTests(unittest.TestCase):
    def setUp(self) -> None:
        state.reset_for_tests()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        state.reset_for_tests()

    def _window_headers(self) -> dict[str, str]:
        payload = self.client.post("/local-api/window-session/open", json={}).json()
        return {"X-Window-Session-Id": payload["session_id"]}

    def _seed_auth(self) -> None:
        state.set_auth(
            "token-1",
            {
                "id": "user-1",
                "email": "seller@example.com",
                "display_name": "Seller One",
                "role": "seller",
                "status": "active",
            },
            "2026-04-07T23:00:00Z",
        )

    def _wait_for_job(self, headers: dict[str, str], job_id: str) -> dict[str, object]:
        for _ in range(20):
            job = self.client.get(f"/local-api/jobs/{job_id}", headers=headers)
            self.assertEqual(job.status_code, 200, job.text)
            payload = job.json()
            if payload["status"] in {"succeeded", "failed"}:
                return payload
            time.sleep(0.05)
        self.fail(f"job {job_id} did not finish in time")

    def test_root_returns_minimal_seller_page(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Windows 卖家本地客户端", response.text)
        self.assertIn("准备本机 WG 配置", response.text)
        self.assertIn("执行受控加入评估", response.text)
        self.assertIn("验证 Manager Task", response.text)
        self.assertIn("发送给本地助手", response.text)

    def test_start_attach_and_assistant_flow(self) -> None:
        headers = self._window_headers()
        login_payload = {
            "access_token": "token-1",
            "expires_at": "2026-04-07T23:00:00Z",
            "user": {
                "id": "user-1",
                "email": "seller@example.com",
                "display_name": "Seller One",
                "role": "seller",
                "status": "active",
                "created_at": "2026-04-07T15:00:00Z",
                "updated_at": "2026-04-07T15:00:00Z",
            },
        }
        session_payload = sample_session_payload()

        with (
            patch("seller_client_app.main.BackendClient.login", return_value=login_payload),
            patch(
                "seller_client_app.main.BackendClient.create_onboarding_session",
                return_value=session_payload,
            ) as create_onboarding_session,
            patch("seller_client_app.main.BackendClient.get_onboarding_session", return_value=session_payload),
            patch("seller_client_app.main.prepare_codex_session", side_effect=lambda **_: state.session_paths(session_payload["session_id"])),
            patch("seller_client_app.main.execute_assistant_request", return_value={"assistant_message": "state looks good"}),
        ):
            login = self.client.post(
                "/local-api/auth/login",
                headers=headers,
                json={"email": "seller@example.com", "password": "password123"},
            )
            self.assertEqual(login.status_code, 200)

            start = self.client.post(
                "/local-api/onboarding/start",
                headers=headers,
                json={"requested_accelerator": "gpu", "requested_compute_node_id": "compute-seller-1"},
            )
            self.assertEqual(start.status_code, 200, start.text)
            start_payload = start.json()
            self.assertEqual(start_payload["session"]["session_id"], "join-session-0001")
            self.assertIn("phase1_drafts", start_payload)
            self.assertIn("linux_host_probe", start_payload["phase1_drafts"]["write_payloads"])
            create_onboarding_session.assert_called_once_with(
                requested_accelerator="gpu",
                requested_compute_node_id="compute-seller-1",
                requested_offer_tier=None,
                expected_wireguard_ip="10.66.66.10",
            )

            state.cleanup_session("join-session-0001")
            attach = self.client.post(
                "/local-api/onboarding/attach",
                headers=headers,
                json={"session_id": "join-session-0001"},
            )
            self.assertEqual(attach.status_code, 200, attach.text)
            self.assertEqual(attach.json()["session"]["session_id"], "join-session-0001")

            assistant = self.client.post(
                "/local-api/assistant/message",
                headers=headers,
                json={"message": "read current onboarding state"},
            )
            self.assertEqual(assistant.status_code, 200, assistant.text)
            job_id = assistant.json()["job_id"]
            payload = self._wait_for_job(headers, job_id)
            self.assertEqual(payload["status"], "succeeded")
            self.assertEqual(payload["result"]["assistant_message"], "state looks good")

    def test_onboarding_start_allows_expected_wireguard_ip_override(self) -> None:
        headers = self._window_headers()
        login_payload = {
            "access_token": "token-1",
            "expires_at": "2026-04-07T23:00:00Z",
            "user": {
                "id": "user-1",
                "email": "seller@example.com",
                "display_name": "Seller One",
                "role": "seller",
                "status": "active",
                "created_at": "2026-04-07T15:00:00Z",
                "updated_at": "2026-04-07T15:00:00Z",
            },
        }
        session_payload = sample_session_payload()

        with (
            patch("seller_client_app.main.BackendClient.login", return_value=login_payload),
            patch(
                "seller_client_app.main.BackendClient.create_onboarding_session",
                return_value=session_payload,
            ) as create_onboarding_session,
            patch(
                "seller_client_app.main.prepare_codex_session",
                side_effect=lambda **_: state.session_paths(session_payload["session_id"]),
            ),
        ):
            login = self.client.post(
                "/local-api/auth/login",
                headers=headers,
                json={"email": "seller@example.com", "password": "password123"},
            )
            self.assertEqual(login.status_code, 200)

            start = self.client.post(
                "/local-api/onboarding/start",
                headers=headers,
                json={
                    "requested_accelerator": "gpu",
                    "requested_compute_node_id": "compute-seller-1",
                    "expected_wireguard_ip": "10.66.66.77",
                },
            )
            self.assertEqual(start.status_code, 200, start.text)
            create_onboarding_session.assert_called_once_with(
                requested_accelerator="gpu",
                requested_compute_node_id="compute-seller-1",
                requested_offer_tier=None,
                expected_wireguard_ip="10.66.66.77",
            )

    def test_correction_and_tcp_validation_are_recorded_locally(self) -> None:
        headers = self._window_headers()
        session_id = f"join-session-correction-{time.time_ns()}"
        state.set_onboarding(sample_session_payload(session_id=session_id))

        correction = self.client.post(
            "/local-api/onboarding/correction",
            headers=headers,
            json={
                "correction_kind": "advertise_override",
                "outcome": "succeeded",
                "reported_phase": "repair",
                "join_mode": "wireguard",
                "observed_wireguard_ip": "10.0.8.12",
                "observed_advertise_addr": "10.0.8.12",
                "observed_data_path_addr": "10.0.8.12",
                "script_path": "Seller_Client/scripts/rejoin-windows-swarm.sh",
                "rollback_path": "D:/AI/Pivot_Client/seller_client/rollback/run-0001",
                "notes": ["record local correction only"],
            },
        )
        self.assertEqual(correction.status_code, 200, correction.text)
        correction_payload = correction.json()
        self.assertEqual(correction_payload["correction"]["correction_kind"], "advertise_override")
        self.assertEqual(correction_payload["correction"]["outcome"], "succeeded")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            host, port = listener.getsockname()
            validation = self.client.post(
                "/local-api/onboarding/tcp-validation",
                headers=headers,
                json={
                    "host": host,
                    "port": port,
                    "target_label": "corrected_seller_target",
                    "notes": ["post-correction tcp probe"],
                },
            )

        self.assertEqual(validation.status_code, 200, validation.text)
        validation_payload = validation.json()
        self.assertTrue(validation_payload["validation"]["reachable"])
        self.assertEqual(validation_payload["validation"]["target_label"], "corrected_seller_target")

        snapshot = self.client.get("/local-api/onboarding/current", headers=headers)
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        runtime_evidence = snapshot.json()["runtime_evidence"]
        self.assertEqual(len(runtime_evidence["correction_history"]), 1)
        self.assertEqual(len(runtime_evidence["tcp_validations"]), 1)
        self.assertEqual(runtime_evidence["latest_correction"]["correction_kind"], "advertise_override")
        self.assertTrue(runtime_evidence["latest_tcp_validation"]["reachable"])

    def test_clear_join_state_job_resets_local_join_records(self) -> None:
        headers = self._window_headers()
        session_id = f"join-session-clear-{time.time_ns()}"
        state.set_onboarding(sample_session_payload(session_id=session_id))
        state.record_correction_evidence(
            {
                "correction_kind": "advertise_override",
                "outcome": "succeeded",
                "notes": ["seed correction"],
            }
        )
        state.record_assistant_run({"assistant_mode": "codex_mcp_stdio_global", "assistant_message": "seed"})

        with (
            patch(
                "seller_client_app.main.perform_clear_join_state",
                return_value={"ok": True, "status": "dry_run", "payload": {"after_state": {"local_node_state": "inactive"}}},
            ),
            patch(
                "seller_client_app.main.collect_environment_health",
                return_value={"summary": {"status": "healthy", "warnings": []}, "docker": {"local_node_state": "inactive"}},
            ),
            patch(
                "seller_client_app.main.BackendClient.get_onboarding_session",
                return_value=sample_session_payload(session_id=session_id, status="verified"),
            ),
        ):
            response = self.client.post("/local-api/runtime/clear-join-state", headers=headers, json={"dry_run": True})
            self.assertEqual(response.status_code, 200, response.text)
            job_id = response.json()["job_id"]
            payload = self._wait_for_job(headers, job_id)
            self.assertEqual(payload["status"], "succeeded")
            self.assertEqual(payload["result"]["clear_join_state"]["status"], "dry_run")

        snapshot = self.client.get("/local-api/onboarding/current", headers=headers)
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        payload = snapshot.json()
        self.assertEqual(payload["runtime_evidence"]["correction_history"], [])
        self.assertIsNone(payload["last_assistant_run"])
        self.assertEqual(payload["last_runtime_workflow"]["kind"], "clear_join_state")

    def test_runtime_routes_cover_wireguard_prep_guided_join_and_manager_task_verification(self) -> None:
        headers = self._window_headers()
        session_id = f"join-session-runtime-{time.time_ns()}"
        self._seed_auth()
        state.set_onboarding(sample_session_payload(session_id=session_id))

        wireguard_result = {
            "ok": True,
            "status": "prepared",
            "source_path": "D:/seller-machine/wg-seller.conf",
            "target_path": "D:/AI/Pivot_Client/seller_client/.cache/seller-zero-flow/wireguard/wg-seller.conf",
            "expected_wireguard_ip": "10.66.66.10",
        }
        health_result = {
            "summary": {"status": "healthy", "warnings": []},
            "docker": {"local_node_state": "active", "node_addr": "10.66.66.10"},
            "wireguard": {"expected_ip": "10.66.66.10", "manager_reachable": True},
        }
        join_result = {
            "ok": True,
            "step": "standard_join_workflow",
            "payload": {
                "effective_target_addr": "10.66.66.1",
                "effective_target_source": "swarm_join_material",
                "success_standard": "docker_swarm_connectivity",
            },
        }
        manager_task_result = {
            "ok": True,
            "step": "manager_task_execution",
            "payload": {
                "completion_standard": "manager_task_execution",
                "task_execution_verified": True,
                "status": "verified",
                "proof_source": "existing_running_task",
            },
        }

        with (
            patch("seller_client_app.main.prepare_machine_wireguard_config", return_value=wireguard_result),
            patch("seller_client_app.main.collect_environment_health", return_value=health_result),
            patch("seller_client_app.main.run_standard_join_workflow", return_value=join_result),
            patch("seller_client_app.main.verify_manager_task_execution", return_value=manager_task_result),
            patch(
                "seller_client_app.main.BackendClient.get_onboarding_session",
                return_value=sample_session_payload(session_id=session_id, status="verified"),
            ),
        ):
            prepare = self.client.post(
                "/local-api/runtime/prepare-wireguard-config",
                headers=headers,
                json={
                    "source_path": "D:/seller-machine/wg-seller.conf",
                    "expected_wireguard_ip": "10.66.66.10",
                },
            )
            self.assertEqual(prepare.status_code, 200, prepare.text)
            prepare_job = self._wait_for_job(headers, prepare.json()["job_id"])
            self.assertEqual(prepare_job["status"], "succeeded")
            self.assertEqual(
                prepare_job["result"]["workflow"]["result"]["target_path"],
                "D:/AI/Pivot_Client/seller_client/.cache/seller-zero-flow/wireguard/wg-seller.conf",
            )

            guided = self.client.post(
                "/local-api/runtime/guided-join-assessment",
                headers=headers,
                json={
                    "expected_wireguard_ip": "10.66.66.10",
                    "wireguard_config_path": "D:/seller-machine/wg-seller.conf",
                },
            )
            self.assertEqual(guided.status_code, 200, guided.text)
            guided_job = self._wait_for_job(headers, guided.json()["job_id"])
            self.assertEqual(guided_job["status"], "succeeded")
            self.assertEqual(
                guided_job["result"]["join_effect"]["success_standard"],
                "manager_task_execution",
            )
            self.assertTrue(guided_job["result"]["manager_task_execution"]["ok"])

            verify = self.client.post(
                "/local-api/runtime/verify-manager-task-execution",
                headers=headers,
                json={},
            )
            self.assertEqual(verify.status_code, 200, verify.text)
            verify_job = self._wait_for_job(headers, verify.json()["job_id"])
            self.assertEqual(verify_job["status"], "succeeded")
            self.assertEqual(
                verify_job["result"]["workflow"]["result"]["payload"]["proof_source"],
                "existing_running_task",
            )

        snapshot = self.client.get("/local-api/onboarding/current", headers=headers)
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        payload = snapshot.json()
        self.assertEqual(payload["local_health_snapshot"]["docker"]["local_node_state"], "active")
        self.assertEqual(payload["last_runtime_workflow"]["kind"], "verify_manager_task_execution")
