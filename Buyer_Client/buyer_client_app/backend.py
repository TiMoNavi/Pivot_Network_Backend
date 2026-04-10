from __future__ import annotations

from typing import Any

import httpx

from buyer_client_app.config import Settings


class BackendClientError(Exception):
    def __init__(self, status_code: int, detail: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.payload = payload or {"detail": detail}


class BackendClient:
    def __init__(
        self,
        settings: Settings,
        token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.token = token
        self.transport = transport

    def with_token(self, token: str | None) -> "BackendClient":
        return BackendClient(self.settings, token=token, transport=self.transport)

    def register(self, email: str, display_name: str, password: str, role: str = "buyer") -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/auth/register",
            json={
                "email": email,
                "display_name": display_name,
                "password": password,
                "role": role,
            },
            include_auth=False,
        )

    def login(self, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/auth/login",
            json={"email": email, "password": password},
            include_auth=False,
        )

    def me(self) -> dict[str, Any]:
        return self._request("GET", f"{self.settings.backend_api_prefix}/auth/me")

    def list_offers(self) -> dict[str, Any]:
        return self._request("GET", f"{self.settings.backend_api_prefix}/offers")

    def get_offer(self, offer_id: str) -> dict[str, Any]:
        return self._request("GET", f"{self.settings.backend_api_prefix}/offers/{offer_id}")

    def create_order(self, offer_id: str, requested_duration_minutes: int) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/orders",
            json={
                "offer_id": offer_id,
                "requested_duration_minutes": requested_duration_minutes,
            },
        )

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"{self.settings.backend_api_prefix}/orders/{order_id}")

    def activate_order(self, order_id: str) -> dict[str, Any]:
        return self._request("POST", f"{self.settings.backend_api_prefix}/orders/{order_id}/activate")

    def list_active_access_grants(self) -> dict[str, Any]:
        return self._request("GET", f"{self.settings.backend_api_prefix}/me/access-grants/active")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        include_auth: bool = True,
    ) -> Any:
        headers: dict[str, str] = {}
        if include_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with httpx.Client(
                base_url=self.settings.backend_base_url,
                timeout=30.0,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = client.request(method, path, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise BackendClientError(502, f"backend_request_failed: {exc}") from exc

        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = {"detail": response.text or "backend_request_failed"}
            detail = payload.get("detail")
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("detail") or str(detail)
            raise BackendClientError(response.status_code, str(detail or "backend_request_failed"), payload)

        if not response.content:
            return {}
        return response.json()
