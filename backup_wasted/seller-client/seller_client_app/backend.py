from __future__ import annotations

from typing import Any

import httpx

from seller_client_app.config import Settings


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

    def with_token(self, token: str | None):
        return BackendClient(self.settings, token=token)

    def login(self, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/auth/login",
            json={"email": email, "password": password},
            include_auth=False,
        )

    def create_onboarding_session(
        self,
        requested_accelerator: str,
        requested_compute_node_id: str | None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions",
            json={
                "requested_accelerator": requested_accelerator,
                "requested_compute_node_id": requested_compute_node_id,
            },
        )

    def get_onboarding_session(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}",
        )

    def get_bootstrap_config(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/bootstrap-config",
        )

    def get_ubuntu_bootstrap(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/ubuntu-bootstrap",
        )

    def post_env_report(self, session_id: str, env_report: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/env-report",
            json={"env_report": env_report},
        )

    def post_host_env_report(self, session_id: str, env_report: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/host-env-report",
            json={"env_report": env_report},
        )

    def post_ubuntu_env_report(self, session_id: str, env_report: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/ubuntu-env-report",
            json={"env_report": env_report},
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

    def post_compute_ready(self, session_id: str, detail: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/onboarding/sessions/{session_id}/compute-ready",
            json={"detail": detail},
        )

    def get_join_material(self, requested_accelerator: str, requested_compute_node_id: str | None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/nodes/register",
            json={
                "requested_accelerator": requested_accelerator,
                "requested_compute_node_id": requested_compute_node_id,
            },
        )

    def claim_node(
        self,
        node_ref: str,
        onboarding_session_id: str,
        compute_node_id: str,
        requested_accelerator: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/nodes/{node_ref}/claim",
            json={
                "onboarding_session_id": onboarding_session_id,
                "compute_node_id": compute_node_id,
                "requested_accelerator": requested_accelerator,
            },
        )

    def get_claim_status(self, node_ref: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/seller/nodes/{node_ref}/claim-status",
        )

    def list_nodes(self) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/seller/nodes",
        )

    def get_runtime_base_images(self) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/seller/runtime-base-images",
        )

    def get_runtime_contract(self) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/seller/runtime-contract",
        )

    def report_image(
        self,
        *,
        node_ref: str,
        runtime_image_ref: str,
        repository: str,
        tag: str,
        registry: str,
        digest: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.settings.backend_api_prefix}/seller/images/report",
            json={
                "node_ref": node_ref,
                "runtime_image_ref": runtime_image_ref,
                "repository": repository,
                "tag": tag,
                "registry": registry,
                "digest": digest,
            },
        )

    def health(self) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.backend_api_prefix}/health",
            include_auth=False,
        )

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
