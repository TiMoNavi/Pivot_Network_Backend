from seller_client_app.main import app


def test_seller_client_routes_use_ubuntu_only_paths() -> None:
    routes = {route.path for route in app.routes}

    assert "/local-api/window-session/open" in routes
    assert "/local-api/window-session/heartbeat" in routes
    assert "/local-api/window-session/close" in routes
    assert "/local-api/windows-host/install-and-check" in routes
    assert "/local-api/ubuntu/standard-image/pull" in routes
    assert "/local-api/ubuntu/standard-image/verify" in routes
    assert "/local-api/ubuntu/swarm-join" in routes
    assert "/local-api/ubuntu/compute-ready" in routes
    assert "/local-api/node/wireguard-status" in routes
    assert "/local-api/ubuntu/image/build" in routes
    assert "/local-api/ubuntu/image/push" in routes
    assert "/local-api/join/run" not in routes
    assert "/local-api/image/build" not in routes
    assert "/local-api/image/push" not in routes
