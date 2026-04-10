from __future__ import annotations

import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.backend import BackendClient
from seller_client_app.config import Settings


class BackendClientTests(unittest.TestCase):
    def test_extended_onboarding_methods_hit_expected_paths(self) -> None:
        captured: list[tuple[str, str, dict | None]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = None
            if request.content:
                payload = request.read().decode("utf-8")
            captured.append((request.method, request.url.path, None if payload is None else {"raw": payload}))
            return httpx.Response(200, json={"ok": True, "path": request.url.path})

        client = BackendClient(
            Settings(backend_base_url="https://pivotcompute.store"),
            token="token-1",
            transport=httpx.MockTransport(handler),
        )

        client.submit_correction("session-1", {"correction_action": "repair"})
        client.reverify_manager_acceptance("session-1", {"node_ref": "node-1"})
        client.submit_authoritative_effective_target("session-1", {"effective_target_addr": "10.66.66.10"})
        client.submit_minimum_tcp_validation("session-1", {"target_port": 8080, "reachable": True})

        self.assertEqual(
            [item[1] for item in captured],
            [
                "/api/v1/seller/onboarding/sessions/session-1/corrections",
                "/api/v1/seller/onboarding/sessions/session-1/re-verify",
                "/api/v1/seller/onboarding/sessions/session-1/authoritative-effective-target",
                "/api/v1/seller/onboarding/sessions/session-1/minimum-tcp-validation",
            ],
        )


if __name__ == "__main__":
    unittest.main()
