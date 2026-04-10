from datetime import UTC, datetime

from backend_app.api.routes.platform import _serialize_platform_node
from backend_app.db.models.swarm import SwarmNode


def test_serialize_platform_node_includes_wireguard_fields() -> None:
    node = SwarmNode(
        cluster_id="00000000-0000-0000-0000-000000000000",
        swarm_node_id="swarm-node-1",
        hostname="seller-ubuntu",
        role="worker",
        status="ready",
        availability="active",
        platform_role="compute",
        compute_enabled=True,
        compute_node_id="compute-seller-1",
        seller_user_id="seller-1",
        accelerator="gpu",
        last_seen_at=datetime.now(UTC),
        raw_payload={"node": {"node_addr": "10.66.66.11"}},
    )

    payload = _serialize_platform_node(node)

    assert payload["node_addr"] == "10.66.66.11"
    assert payload["expected_wireguard_addr"] == "10.66.66.11"
    assert payload["wireguard_addr_match"] is True
    assert payload["network_mode"] == "wireguard"
