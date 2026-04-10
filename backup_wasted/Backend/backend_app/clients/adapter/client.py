from collections.abc import Mapping
from typing import Any

import httpx


class AdapterClientError(Exception):
    def __init__(self, status_code: int, detail: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.payload = payload or {}


class AdapterClient:
    """Small wrapper around the Swarm Adapter HTTP API."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def get_health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def get_swarm_overview(self) -> dict[str, Any]:
        return self._request("GET", "/swarm/overview")

    def list_nodes(self) -> dict[str, Any]:
        return self._request("GET", "/swarm/nodes")

    def inspect_node(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/nodes/inspect", json=payload)

    def get_join_material(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/nodes/join-material", json=payload)

    def claim_node(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/nodes/claim", json=payload)

    def set_node_availability(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/nodes/availability", json=payload)

    def remove_node(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/nodes/remove", json=payload)

    def validate_runtime_image(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/runtime-images/validate", json=payload)

    def probe_node(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/nodes/probe", json=payload)

    def inspect_service(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/services/inspect", json=payload)

    def create_runtime_bundle(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/runtime-session-bundles/create", json=payload)

    def inspect_runtime_bundle(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/runtime-session-bundles/inspect", json=payload)

    def remove_runtime_bundle(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/swarm/runtime-session-bundles/remove", json=payload)

    def apply_wireguard_peer(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/wireguard/peers/apply", json=payload)

    def remove_wireguard_peer(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/wireguard/peers/remove", json=payload)

    def _request(
        self,
        method: str,
        path: str,
        json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            try:
                response = client.request(method, path, json=json, headers=headers)
            except httpx.TimeoutException as exc:
                raise AdapterClientError(504, "adapter_request_timeout") from exc
        if response.is_error:
            payload: dict[str, Any] = {}
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            detail = str(payload.get("detail") or response.text or "adapter_request_failed")
            raise AdapterClientError(response.status_code, detail, payload)

        if not response.content:
            return {}

        return response.json()
