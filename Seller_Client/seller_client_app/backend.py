from __future__ import annotations

from typing import Any

import httpx

from seller_client_app.config import Settings


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

    def register(self, email: str, display_name: str, password: str, role: str = "seller") -> dict[str, Any]:
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

    def create_onboarding_session(
        self,
        *,
        requested_accelerator: str,
        requested_compute_node_id: str | None = None,
        requested_offer_tier: str | None = None,
        expected_wireguard_ip: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "requested_accelerator": requested_accelerator,
            "requested_compute_node_id": requested_compute_node_id,
            "requested_offer_tier": requested_offer_tier,
        }
        if expected_wireguard_ip is not None:
            payload["expected_wireguard_ip"] = expected_wireguard_ip
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions",
            json=payload,
        )

    def get_onboarding_session(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}",
        )

    def submit_linux_host_probe(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/linux-host-probe",
            json=payload,
        )

    def submit_linux_substrate_probe(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/linux-substrate-probe",
            json=payload,
        )

    def submit_container_runtime_probe(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/container-runtime-probe",
            json=payload,
        )

    def submit_join_complete(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/join-complete",
            json=payload,
        )

    def submit_correction(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/corrections",
            json=payload,
        )

    def reverify_manager_acceptance(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/re-verify",
            json=payload,
        )

    def submit_authoritative_effective_target(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/authoritative-effective-target",
            json=payload,
        )

    def submit_minimum_tcp_validation(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/minimum-tcp-validation",
            json=payload,
        )

    def heartbeat_onboarding_session(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/heartbeat",
        )

    def close_onboarding_session(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/close",
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
