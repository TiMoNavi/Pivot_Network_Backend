from __future__ import annotations

from typing import Any

import httpx

from buyer_client_app.config import Settings


class BackendClientError(Exception):
    def __init__(self, status_code: int, detail: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.payload = payload or {}


class BackendClient:
    def __init__(self, settings: Settings, token: str | None = None) -> None:
        self.settings = settings
        self.token = token

    def login(self, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/auth/login",
            json={"email": email, "password": password},
            include_auth=False,
        )

    def catalog_offers(self) -> list[dict[str, Any]]:
        return self._request("GET", f"{self.settings.backend_api_prefix}/buyer/catalog/offers")

    def create_order(self, offer_id: str, requested_duration_minutes: int) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/buyer/orders",
            json={"offer_id": offer_id, "requested_duration_minutes": requested_duration_minutes},
        )

    def redeem_access_code(self, access_code: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/buyer/access-codes/redeem",
            json={"access_code": access_code},
        )

    def create_runtime_session(self, access_code: str, wireguard_public_key: str, network_mode: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/buyer/runtime-sessions",
            json={
                "access_code": access_code,
                "network_mode": network_mode,
                "wireguard_public_key": wireguard_public_key,
            },
        )

    def get_runtime_session(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"{self.settings.backend_api_prefix}/buyer/runtime-sessions/{session_id}")

    def get_connect_material(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/buyer/runtime-sessions/{session_id}/connect-material",
        )

    def stop_runtime_session(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/buyer/runtime-sessions/{session_id}/stop",
        )

    def get_bootstrap_config(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/buyer/runtime-sessions/{session_id}/bootstrap-config",
        )

    def get_client_session(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/buyer/runtime-sessions/{session_id}/client-session",
        )

    def post_env_report(self, session_id: str, env_report: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/buyer/runtime-sessions/{session_id}/env-report",
            json={"env_report": env_report},
        )

    def heartbeat(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/buyer/runtime-sessions/{session_id}/heartbeat",
        )

    def close_runtime_session(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/buyer/runtime-sessions/{session_id}/close",
        )

    def health(self) -> dict[str, Any]:
        return self._request("GET", f"{self.settings.backend_api_prefix}/health", include_auth=False)

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
                timeout=60.0,
                trust_env=False,
            ) as client:
                response = client.request(method, path, json=json, headers=headers)
        except httpx.HTTPError as exc:  # noqa: BLE001
            raise BackendClientError(502, f"backend_request_failed: {exc}") from exc

        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = {"detail": response.text or "backend_request_failed"}
            detail = str(payload.get("detail") or "backend_request_failed")
            raise BackendClientError(response.status_code, detail, payload)

        if not response.content:
            return {}
        return response.json()
