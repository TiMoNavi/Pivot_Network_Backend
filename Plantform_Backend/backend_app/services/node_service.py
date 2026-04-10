from __future__ import annotations

from datetime import UTC, datetime

from backend_app.clients.adapter_client import AdapterClient, NodeSearchFilters
from backend_app.schemas.health import AdapterHealthRead
from backend_app.schemas.nodes import (
    NodeDetailRead,
    NodeListRead,
    NodePollSnapshotRead,
    NodeSummaryRead,
    NodeTaskRead,
    SwarmOverviewRead,
    SwarmServiceRead,
    SwarmStateRead,
)


class NodeService:
    def __init__(self, adapter_client: AdapterClient) -> None:
        self.adapter_client = adapter_client

    def get_adapter_health(self) -> AdapterHealthRead:
        payload = self.adapter_client.get_health()
        return AdapterHealthRead(
            status=str(payload.get("status") or "unknown"),
            adapter_name=payload.get("adapter_name"),
            swarm_manager_addr=payload.get("swarm_manager_addr"),
            wireguard_interface=payload.get("wireguard_interface"),
            portainer_url=payload.get("portainer_url"),
        )

    def get_overview(self) -> SwarmOverviewRead:
        payload = self.adapter_client.get_swarm_overview()
        return SwarmOverviewRead(
            manager_host=str(payload.get("manager_host") or ""),
            swarm=SwarmStateRead(**payload.get("swarm", {})),
            node_list_summary=[self._node_summary(item) for item in payload.get("node_list_summary", [])],
            service_list_summary=[SwarmServiceRead(**item) for item in payload.get("service_list_summary", [])],
        )

    def list_nodes(
        self,
        *,
        query: str | None = None,
        seller_user_id: str | None = None,
        compute_node_id: str | None = None,
        role: str | None = None,
        status: str | None = None,
        availability: str | None = None,
        accelerator: str | None = None,
        compute_enabled: bool | None = None,
    ) -> NodeListRead:
        filters = NodeSearchFilters(
            query=query,
            seller_user_id=seller_user_id,
            compute_node_id=compute_node_id,
            role=role,
            status=status,
            availability=availability,
            accelerator=accelerator,
            compute_enabled=compute_enabled,
        )
        payload = self.adapter_client.search_nodes(filters)
        items = [self._node_summary(item) for item in payload.get("nodes", [])]
        return NodeListRead(
            items=items,
            total=int(payload.get("total", len(items))),
            query=payload.get("query"),
            applied_filters=payload.get("applied_filters") or filters.as_query_params(),
        )

    def get_node_detail(self, node_ref: str) -> NodeDetailRead:
        payload = self.adapter_client.inspect_node(node_ref)
        return self._node_detail(payload)

    def get_node_detail_by_compute_node_id(self, compute_node_id: str) -> NodeDetailRead:
        payload = self.adapter_client.inspect_node_by_compute_node_id(compute_node_id)
        return self._node_detail(payload)

    def poll_snapshot(
        self,
        *,
        query: str | None = None,
        seller_user_id: str | None = None,
        compute_node_id: str | None = None,
        role: str | None = None,
        status: str | None = None,
        availability: str | None = None,
        accelerator: str | None = None,
        compute_enabled: bool | None = None,
    ) -> NodePollSnapshotRead:
        return NodePollSnapshotRead(
            polled_at=datetime.now(UTC),
            adapter_health=self.get_adapter_health(),
            overview=self.get_overview(),
            nodes=self.list_nodes(
                query=query,
                seller_user_id=seller_user_id,
                compute_node_id=compute_node_id,
                role=role,
                status=status,
                availability=availability,
                accelerator=accelerator,
                compute_enabled=compute_enabled,
            ),
        )

    @staticmethod
    def _node_summary(payload: dict) -> NodeSummaryRead:
        return NodeSummaryRead(
            id=str(payload.get("id") or ""),
            hostname=str(payload.get("hostname") or ""),
            role=str(payload.get("role") or ""),
            status=str(payload.get("status") or ""),
            availability=str(payload.get("availability") or ""),
            node_addr=payload.get("node_addr"),
            platform_role=payload.get("platform_role"),
            compute_enabled=bool(payload.get("compute_enabled")),
            compute_node_id=payload.get("compute_node_id"),
            seller_user_id=payload.get("seller_user_id"),
            accelerator=payload.get("accelerator"),
            running_tasks=int(payload.get("running_tasks") or 0),
        )

    def _node_detail(self, payload: dict) -> NodeDetailRead:
        return NodeDetailRead(
            node=self._node_summary(payload.get("node", {})),
            platform_labels=payload.get("platform_labels") or {},
            raw_labels=payload.get("raw_labels") or {},
            tasks=[
                NodeTaskRead(
                    id=item.get("id"),
                    name=str(item.get("name") or ""),
                    image=item.get("image"),
                    desired_state=str(item.get("desired_state") or ""),
                    current_state=str(item.get("current_state") or ""),
                    error=item.get("error"),
                    ports=item.get("ports"),
                )
                for item in payload.get("tasks", [])
            ],
            recent_error_summary=payload.get("recent_error_summary") or [],
        )
