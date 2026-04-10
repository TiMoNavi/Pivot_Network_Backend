from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class AdapterClientError(Exception):
    def __init__(self, status_code: int, detail: str, payload: Any | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.payload = payload


@dataclass
class NodeSearchFilters:
    query: str | None = None
    seller_user_id: str | None = None
    compute_node_id: str | None = None
    role: str | None = None
    status: str | None = None
    availability: str | None = None
    accelerator: str | None = None
    compute_enabled: bool | None = None

    def as_query_params(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "query": self.query,
                "seller_user_id": self.seller_user_id,
                "compute_node_id": self.compute_node_id,
                "role": self.role,
                "status": self.status,
                "availability": self.availability,
                "accelerator": self.accelerator,
                "compute_enabled": self.compute_enabled,
            }.items()
            if value is not None
        }


class AdapterClient:
    def __init__(self, *, base_url: str, token: str, timeout_seconds: int = 15) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def get_health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def get_swarm_overview(self) -> dict[str, Any]:
        return self._request("GET", "/swarm/overview", auth_required=True)

    def list_nodes(self) -> dict[str, Any]:
        return self._request("GET", "/swarm/nodes", auth_required=True)

    def search_nodes(self, filters: NodeSearchFilters) -> dict[str, Any]:
        try:
            return self._request(
                "GET",
                "/swarm/nodes/search",
                params=filters.as_query_params(),
                auth_required=True,
            )
        except AdapterClientError as exc:
            if exc.status_code != 404:
                raise

        nodes = self.list_nodes().get("nodes", [])
        filtered = self._filter_node_summaries(nodes, filters)
        return {
            "nodes": filtered,
            "total": len(filtered),
            "query": filters.query,
            "applied_filters": filters.as_query_params(),
        }

    def get_join_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/swarm/nodes/join-material",
            json=payload,
            auth_required=True,
        )

    def claim_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/swarm/nodes/claim",
            json=payload,
            auth_required=True,
        )

    def inspect_node(self, node_ref: str) -> dict[str, Any]:
        try:
            return self._request(
                "GET",
                f"/swarm/nodes/by-ref/{node_ref}",
                auth_required=True,
            )
        except AdapterClientError as exc:
            if exc.status_code != 404:
                raise

        return self._request(
            "POST",
            "/swarm/nodes/inspect",
            json={"node_ref": node_ref},
            auth_required=True,
        )

    def inspect_node_by_compute_node_id(self, compute_node_id: str) -> dict[str, Any]:
        try:
            return self._request(
                "GET",
                f"/swarm/nodes/by-compute-node-id/{compute_node_id}",
                auth_required=True,
            )
        except AdapterClientError as exc:
            if exc.status_code != 404:
                raise

        filtered = self.search_nodes(NodeSearchFilters(compute_node_id=compute_node_id)).get("nodes", [])
        if not filtered:
            raise AdapterClientError(404, "compute_node_id_not_found", {"detail": "compute_node_id_not_found"})
        return self.inspect_node(filtered[0]["id"])

    def probe_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/swarm/nodes/probe",
            json=payload,
            auth_required=True,
        )

    def validate_runtime_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/swarm/runtime-images/validate",
            json=payload,
            auth_required=True,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        auth_required: bool = False,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if auth_required and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(
                    method,
                    f"{self.base_url}{path}",
                    params=params,
                    json=json,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise AdapterClientError(503, "adapter_request_failed") from exc

        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = {"detail": response.text}

        if response.is_error:
            detail = payload.get("detail") if isinstance(payload, dict) else response.text
            raise AdapterClientError(response.status_code, str(detail), payload)

        if not isinstance(payload, dict):
            raise AdapterClientError(502, "adapter_response_invalid", payload)
        return payload

    @staticmethod
    def _filter_node_summaries(nodes: list[dict[str, Any]], filters: NodeSearchFilters) -> list[dict[str, Any]]:
        query = (filters.query or "").strip().lower()

        def matches(node: dict[str, Any]) -> bool:
            if filters.seller_user_id and str(node.get("seller_user_id") or "") != filters.seller_user_id:
                return False
            if filters.compute_node_id and str(node.get("compute_node_id") or "") != filters.compute_node_id:
                return False
            if filters.role and str(node.get("role") or "").lower() != filters.role.lower():
                return False
            if filters.status and str(node.get("status") or "").lower() != filters.status.lower():
                return False
            if filters.availability and str(node.get("availability") or "").lower() != filters.availability.lower():
                return False
            if filters.accelerator and str(node.get("accelerator") or "").lower() != filters.accelerator.lower():
                return False
            if filters.compute_enabled is not None and bool(node.get("compute_enabled")) != filters.compute_enabled:
                return False
            if query:
                haystack = " ".join(
                    [
                        str(node.get("id") or ""),
                        str(node.get("hostname") or ""),
                        str(node.get("node_addr") or ""),
                        str(node.get("platform_role") or ""),
                        str(node.get("compute_node_id") or ""),
                        str(node.get("seller_user_id") or ""),
                        str(node.get("accelerator") or ""),
                    ]
                ).lower()
                if query not in haystack:
                    return False
            return True

        return [node for node in nodes if matches(node)]
