from app.services import swarm_adapter


def test_swarm_health_endpoint_returns_adapter_status(client, monkeypatch) -> None:
    expected_payload = {
        "status": "ok",
        "adapter": "docker-cli",
        "reachable": True,
        "swarm": {
            "state": "active",
            "node_id": "node-1",
            "node_addr": "192.168.65.3",
            "control_available": True,
            "error": None,
        },
    }

    monkeypatch.setattr(
        swarm_adapter,
        "get_swarm_health",
        lambda: expected_payload,
    )

    response = client.get("/api/v1/swarm/health")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_swarm_health_endpoint_returns_503_when_adapter_unavailable(
    client, monkeypatch
) -> None:
    def raise_unavailable() -> None:
        raise swarm_adapter.SwarmAdapterUnavailableError("docker socket is unavailable")

    monkeypatch.setattr(swarm_adapter, "get_swarm_health", raise_unavailable)

    response = client.get("/api/v1/swarm/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "adapter": "docker-cli",
        "reachable": False,
        "detail": "docker socket is unavailable",
    }
