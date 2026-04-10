from __future__ import annotations

import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.backend import BackendClient
from buyer_client_app.config import Settings


class BackendClientTests(unittest.TestCase):
    def test_trade_methods_hit_expected_paths(self) -> None:
        captured: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append((request.method, request.url.path))
            return httpx.Response(200, json={"ok": True, "path": request.url.path})

        client = BackendClient(
            Settings(backend_base_url="https://pivotcompute.store"),
            token="token-1",
            transport=httpx.MockTransport(handler),
        )

        client.list_offers()
        client.get_offer("offer-1")
        client.create_order("offer-1", 60)
        client.get_order("order-1")
        client.activate_order("order-1")
        client.list_active_access_grants()

        self.assertEqual(
            captured,
            [
                ("GET", "/api/v1/offers"),
                ("GET", "/api/v1/offers/offer-1"),
                ("POST", "/api/v1/orders"),
                ("GET", "/api/v1/orders/order-1"),
                ("POST", "/api/v1/orders/order-1/activate"),
                ("GET", "/api/v1/me/access-grants/active"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
