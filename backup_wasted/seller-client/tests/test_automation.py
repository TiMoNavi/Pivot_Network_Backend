from seller_client_app import automation
from seller_client_app.config import Settings


class FakeBackendClient:
    def __init__(self, order: list[str]) -> None:
        self.order = order

    def get_ubuntu_bootstrap(self, session_id: str):  # noqa: ANN001
        self.order.append("get_ubuntu_bootstrap")
        return {
            "session_id": session_id,
            "ubuntu_compute_bootstrap": {
                "expected_node_addr": "10.66.66.11",
                "swarm_join": {"manager_addr": "10.66.66.1", "manager_port": 2377},
            },
        }

    def post_compute_ready(self, session_id: str, detail: dict):  # noqa: ANN001
        self.order.append("post_compute_ready")
        return {"session_id": session_id, "status": "compute_ready", "detail": detail}

    def claim_node(self, **kwargs):  # noqa: ANN003
        self.order.append("claim_node")
        return {"status": "claimed", **kwargs}

    def get_claim_status(self, node_ref: str):  # noqa: ANN001
        self.order.append("get_claim_status")
        return {"node_ref": node_ref, "claimed": True}


def test_sell_my_compute_full_auto_orders_steps(monkeypatch) -> None:
    order: list[str] = []
    backend = FakeBackendClient(order)

    monkeypatch.setattr(automation, "detect_ubuntu_swarm_node_ref", lambda settings: "node-1")
    monkeypatch.setattr(automation, "detect_ubuntu_swarm_info", lambda settings: {"swarm": "ok"})

    def windows_install(settings, mode="all"):  # noqa: ANN001
        order.append(f"windows_install:{mode}")
        return {"status": "ok"}

    def ubuntu_bootstrap_runner(settings, ubuntu_bootstrap):  # noqa: ANN001
        order.append("ubuntu_bootstrap")
        return {"status": "bootstrapped"}

    def standard_image_pull(settings, ubuntu_bootstrap):  # noqa: ANN001
        order.append("standard_image_pull")
        return {"status": "pulled"}

    def standard_image_verify(settings, ubuntu_bootstrap, session_id, requested_accelerator):  # noqa: ANN001
        order.append(f"standard_image_verify:{requested_accelerator}")
        return {"status": "verified", "session_id": session_id}

    def join_runner(settings, ubuntu_bootstrap):  # noqa: ANN001
        order.append("join")
        return {"status": "joined"}

    def node_status_runner(settings, expected_node_addr, backend_client=None, node_ref=None):  # noqa: ANN001
        order.append("node_status")
        return {
            "expected_node_addr": expected_node_addr,
            "local_node_addr": expected_node_addr,
            "platform_node_addr": expected_node_addr,
            "wireguard_addr_match": True,
        }

    result = automation.sell_my_compute_full_auto(
        settings=Settings(),
        backend_client=backend,
        onboarding_session={
            "session_id": "session-1",
            "requested_accelerator": "gpu",
            "requested_compute_node_id": "compute-seller-1",
        },
        windows_install_and_check=windows_install,
        ubuntu_bootstrap_runner=ubuntu_bootstrap_runner,
        standard_image_pull_runner=standard_image_pull,
        standard_image_verify_runner=standard_image_verify,
        join_runner=join_runner,
        node_status_runner=node_status_runner,
    )

    assert result["status"] == "seller_compute_ready"
    assert order == [
        "get_ubuntu_bootstrap",
        "windows_install:all",
        "ubuntu_bootstrap",
        "standard_image_pull",
        "standard_image_verify:gpu",
        "join",
        "node_status",
        "post_compute_ready",
        "claim_node",
        "get_claim_status",
    ]
