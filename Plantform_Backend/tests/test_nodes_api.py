from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend_app.api.deps import get_node_service
from backend_app.main import app
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


class FakeNodeService:
    def get_adapter_health(self) -> AdapterHealthRead:
        return AdapterHealthRead(
            status="ok",
            adapter_name="swarm-adapter",
            swarm_manager_addr="81.70.52.75",
            wireguard_interface="wg0",
        )

    def get_overview(self) -> SwarmOverviewRead:
        node = NodeSummaryRead(
            id="node-1",
            hostname="seller-node-1",
            role="worker",
            status="ready",
            availability="active",
            node_addr="10.0.8.12",
            platform_role="compute",
            compute_enabled=True,
            compute_node_id="compute-seller-1",
            seller_user_id="seller-1",
            accelerator="gpu",
            running_tasks=1,
        )
        return SwarmOverviewRead(
            manager_host="81.70.52.75",
            swarm=SwarmStateRead(
                state="active",
                node_id="manager-1",
                node_addr="81.70.52.75",
                control_available=True,
                nodes=2,
                managers=1,
            ),
            node_list_summary=[node],
            service_list_summary=[
                SwarmServiceRead(
                    id="svc-1",
                    name="portainer_portainer",
                    mode="replicated",
                    replicas="1/1",
                    image="portainer/portainer-ce:lts",
                    ports="9443:9443",
                )
            ],
        )

    def list_nodes(self, **filters) -> NodeListRead:
        node = NodeSummaryRead(
            id="node-1",
            hostname="seller-node-1",
            role="worker",
            status="ready",
            availability="active",
            node_addr="10.0.8.12",
            platform_role="compute",
            compute_enabled=True,
            compute_node_id="compute-seller-1",
            seller_user_id="seller-1",
            accelerator="gpu",
            running_tasks=1,
        )
        return NodeListRead(
            items=[node],
            total=1,
            query=filters.get("query"),
            applied_filters={key: value for key, value in filters.items() if value is not None},
        )

    def get_node_detail(self, node_ref: str) -> NodeDetailRead:
        del node_ref
        return NodeDetailRead(
            node=self.list_nodes().items[0],
            platform_labels={"platform.role": "compute"},
            raw_labels={"platform.role": "compute"},
            tasks=[
                NodeTaskRead(
                    id="task-1",
                    name="runtime-abc.1",
                    image="registry.example.com/runtime:v1",
                    desired_state="Running",
                    current_state="Running 10 seconds ago",
                    error=None,
                    ports=None,
                )
            ],
            recent_error_summary=[],
        )

    def get_node_detail_by_compute_node_id(self, compute_node_id: str) -> NodeDetailRead:
        del compute_node_id
        return self.get_node_detail("node-1")

    def poll_snapshot(self, **filters) -> NodePollSnapshotRead:
        return NodePollSnapshotRead(
            polled_at=datetime.now(UTC),
            adapter_health=self.get_adapter_health(),
            overview=self.get_overview(),
            nodes=self.list_nodes(**filters),
        )


def test_platform_node_endpoints() -> None:
    app.dependency_overrides[get_node_service] = lambda: FakeNodeService()
    client = TestClient(app)

    health = client.get("/api/v1/health")
    assert health.status_code == 200, health.text

    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200, ready.text
    assert ready.json()["adapter"]["status"] == "ok"

    adapter_health = client.get("/api/v1/adapter/health")
    assert adapter_health.status_code == 200, adapter_health.text

    nodes = client.get("/api/v1/platform/nodes")
    assert nodes.status_code == 200, nodes.text
    nodes_payload = nodes.json()
    assert nodes_payload["total"] == 1
    assert nodes_payload["items"][0]["hostname"] == "seller-node-1"

    search = client.get("/api/v1/platform/nodes/search", params={"query": "seller"})
    assert search.status_code == 200, search.text
    assert search.json()["query"] == "seller"

    detail = client.get("/api/v1/platform/nodes/node-1")
    assert detail.status_code == 200, detail.text
    assert detail.json()["node"]["id"] == "node-1"

    compute_detail = client.get("/api/v1/platform/nodes/by-compute-node-id/compute-seller-1")
    assert compute_detail.status_code == 200, compute_detail.text
    assert compute_detail.json()["node"]["compute_node_id"] == "compute-seller-1"

    poll = client.get("/api/v1/platform/swarm/poll-snapshot")
    assert poll.status_code == 200, poll.text
    assert poll.json()["nodes"]["total"] == 1

    app.dependency_overrides.clear()
