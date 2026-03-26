from fastapi.testclient import TestClient

import buyer_client.agent_server as agent_server


def test_buyer_agent_server_health() -> None:
    client = TestClient(agent_server.app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_buyer_agent_server_serves_index_page() -> None:
    client = TestClient(agent_server.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "Pivot Buyer Console" in response.text


def test_buyer_dashboard_returns_local_sessions(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "SESSION_STORE",
        {
            "local-1": {
                "local_id": "local-1",
                "backend_url": "http://127.0.0.1:8011",
                "buyer_email": "buyer@example.com",
                "buyer_token": "secret",
                "session_id": 1,
                "seller_node_key": "node-001",
                "runtime_image": "python:3.12-alpine",
                "code_filename": "main.py",
                "status": "completed",
                "logs": "hello\n42\n",
                "relay_endpoint": "relay://buyer-runtime-session/1",
                "connect_code": "abc123",
                "created_at": "2026-03-25T00:00:00Z",
                "ended_at": "2026-03-25T00:00:10Z",
            }
        },
    )
    monkeypatch.setattr(agent_server, "_read_activity", lambda state_dir, limit=20: [])

    client = TestClient(agent_server.app)
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["session_count"] == 1
    assert payload["sessions"][0]["seller_node_key"] == "node-001"


def test_buyer_run_code_creates_local_session(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "create_runtime_session",
        lambda **kwargs: {
            "backend_url": kwargs["backend_url"],
            "buyer_email": kwargs["email"],
            "buyer_token": "buyer-token",
            "session_id": 7,
            "seller_node_key": kwargs["seller_node_key"],
            "runtime_image": kwargs["runtime_image"],
            "code_filename": kwargs["code_filename"],
            "session_mode": "code_run",
            "connect_code": "connect-code",
            "session_token": "session-token",
            "relay_endpoint": "relay://buyer-runtime-session/7",
            "create_result": {"data": {"session_id": 7}},
            "redeem_result": {"data": {"status": "created"}},
            "auth": {},
        },
    )

    client = TestClient(agent_server.app)
    response = client.post(
        "/api/runtime/run-code",
        json={
            "backend_url": "http://127.0.0.1:8011",
            "email": "buyer@example.com",
            "password": "super-secret-password",
            "seller_node_key": "node-001",
            "runtime_image": "python:3.12-alpine",
            "code_filename": "main.py",
            "code_content": "print('hello')",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["session_id"] == 7
    assert payload["session"]["seller_node_key"] == "node-001"


def test_buyer_start_shell_creates_local_shell_session(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "start_shell_session",
        lambda **kwargs: {
            "backend_url": kwargs["backend_url"],
            "buyer_email": kwargs["email"],
            "buyer_token": "buyer-token",
            "session_id": 8,
            "seller_node_key": kwargs["seller_node_key"],
            "runtime_image": kwargs["runtime_image"],
            "code_filename": "__shell__",
            "session_mode": "shell",
            "connect_code": "connect-code",
            "session_token": "session-token",
            "relay_endpoint": "relay://buyer-runtime-session/8",
            "create_result": {"data": {"session_id": 8}},
            "redeem_result": {"data": {"status": "running"}},
            "auth": {},
        },
    )

    client = TestClient(agent_server.app)
    response = client.post(
        "/api/runtime/start-shell",
        json={
            "backend_url": "http://127.0.0.1:8011",
            "email": "buyer@example.com",
            "password": "super-secret-password",
            "seller_node_key": "node-001",
            "runtime_image": "python:3.12-alpine",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["session_id"] == 8
    assert payload["session"]["session_mode"] == "shell"


def test_buyer_run_archive_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "run_archive",
        lambda **kwargs: {
            "session_id": 10,
            "status": "completed",
            "logs": "archive run ok",
        },
    )

    client = TestClient(agent_server.app)
    response = client.post(
        "/api/runtime/run-archive",
        json={
            "backend_url": "http://127.0.0.1:8011",
            "email": "buyer@example.com",
            "password": "super-secret-password",
            "seller_node_key": "node-001",
            "source_path": "d:/tmp/demo.zip",
            "runtime_image": "python:3.12-alpine",
            "run_command": "python main.py",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["status"] == "completed"
    assert "archive run ok" in payload["result"]["logs"]


def test_buyer_run_github_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "run_github_repo",
        lambda **kwargs: {
            "session_id": 11,
            "status": "completed",
            "logs": "github run ok",
        },
    )

    client = TestClient(agent_server.app)
    response = client.post(
        "/api/runtime/run-github",
        json={
            "backend_url": "http://127.0.0.1:8011",
            "email": "buyer@example.com",
            "password": "super-secret-password",
            "seller_node_key": "node-001",
            "repo_url": "https://github.com/example/repo",
            "repo_ref": "main",
            "runtime_image": "python:3.12-alpine",
            "run_command": "python main.py",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["status"] == "completed"
    assert "github run ok" in payload["result"]["logs"]


def test_buyer_refresh_session_reads_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "SESSION_STORE",
        {
            "local-1": {
                "local_id": "local-1",
                "backend_url": "http://127.0.0.1:8011",
                "buyer_email": "buyer@example.com",
                "buyer_token": "buyer-token",
                "session_id": 3,
                "seller_node_key": "node-001",
                "runtime_image": "python:3.12-alpine",
                "code_filename": "main.py",
                "session_mode": "code_run",
                "status": "created",
                "logs": "",
                "relay_endpoint": "relay://buyer-runtime-session/3",
                "connect_code": "abc123",
                "created_at": "2026-03-25T00:00:00Z",
                "ended_at": None,
            }
        },
    )
    monkeypatch.setattr(
        agent_server,
        "read_runtime_session",
        lambda **kwargs: {
            "session_id": 3,
            "seller_node_key": "node-001",
            "runtime_image": "python:3.12-alpine",
            "code_filename": "main.py",
            "session_mode": "code_run",
            "status": "completed",
            "service_name": "buyer-runtime-test",
            "relay_endpoint": "relay://buyer-runtime-session/3",
            "logs": "hello\n42\n",
            "ended_at": "2026-03-25T00:00:10Z",
        },
    )

    client = TestClient(agent_server.app)
    response = client.get("/api/runtime/sessions/local-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["status"] == "completed"
    assert "42" in payload["session"]["logs"]


def test_buyer_exec_session_runs_local_command(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "SESSION_STORE",
        {
            "local-1": {
                "local_id": "local-1",
                "backend_url": "http://127.0.0.1:8011",
                "buyer_email": "buyer@example.com",
                "buyer_token": "buyer-token",
                "session_id": 9,
                "seller_node_key": "node-001",
                "runtime_image": "python:3.12-alpine",
                "code_filename": "__shell__",
                "session_mode": "shell",
                "status": "running",
                "service_name": "buyer-runtime-shell",
                "logs": "",
                "relay_endpoint": "relay://buyer-runtime-session/9",
                "connect_code": "abc123",
                "created_at": "2026-03-25T00:00:00Z",
                "ended_at": None,
            }
        },
    )
    monkeypatch.setattr(
        agent_server,
        "_refresh_session",
        lambda local_id: agent_server._masked_session(agent_server.SESSION_STORE[local_id]),
    )
    monkeypatch.setattr(
        agent_server,
        "exec_runtime_command_locally",
        lambda service_name, command, wait_seconds=20: {
            "ok": True,
            "service_name": service_name,
            "stdout": "Python 3.12.0\n",
            "stderr": "",
            "exit_code": 0,
        },
    )

    client = TestClient(agent_server.app)
    response = client.post(
        "/api/runtime/sessions/local-1/exec",
        json={"command": "python -V"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "Python 3.12.0" in payload["session"]["logs"]


def test_buyer_wireguard_bootstrap_endpoint_updates_local_session(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "SESSION_STORE",
        {
            "local-1": {
                "local_id": "local-1",
                "state_dir": "d:/tmp/buyer-state",
                "backend_url": "http://127.0.0.1:8011",
                "buyer_email": "buyer@example.com",
                "buyer_token": "buyer-token",
                "session_id": 12,
                "seller_node_key": "node-001",
                "runtime_image": "python:3.12-alpine",
                "code_filename": "__shell__",
                "session_mode": "shell",
                "network_mode": "wireguard",
                "status": "running",
                "service_name": "buyer-runtime-shell",
                "logs": "",
                "relay_endpoint": "relay://buyer-runtime-session/12",
                "connect_code": "abc123",
                "created_at": "2026-03-25T00:00:00Z",
                "expires_at": "2026-03-25T01:00:00Z",
                "ended_at": None,
            }
        },
    )
    monkeypatch.setattr(
        agent_server,
        "bootstrap_runtime_session_wireguard",
        lambda **kwargs: {
            "bundle": {
                "interface_name": "wg-buyer",
                "client_address": "10.66.66.129/32",
                "seller_wireguard_target": "10.66.66.10",
            },
            "activation_result": {"ok": True, "mode": "elevated_helper"},
        },
    )
    monkeypatch.setattr(
        agent_server,
        "wireguard_summary",
        lambda interface_name="wg-buyer", state_dir=None: {"ok": True, "config_path": "d:/tmp/wg-buyer.conf"},
    )

    client = TestClient(agent_server.app)
    response = client.post("/api/runtime/sessions/local-1/wireguard/bootstrap", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["session"]["wireguard_status"] == "active"
    assert payload["session"]["wireguard_client_address"] == "10.66.66.129/32"
    assert payload["session"]["seller_wireguard_target"] == "10.66.66.10"


def test_buyer_renew_endpoint_updates_expiry(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "SESSION_STORE",
        {
            "local-1": {
                "local_id": "local-1",
                "state_dir": "d:/tmp/buyer-state",
                "backend_url": "http://127.0.0.1:8011",
                "buyer_email": "buyer@example.com",
                "buyer_token": "buyer-token",
                "session_id": 13,
                "seller_node_key": "node-001",
                "runtime_image": "python:3.12-alpine",
                "code_filename": "__shell__",
                "session_mode": "shell",
                "network_mode": "wireguard",
                "status": "running",
                "service_name": "buyer-runtime-shell",
                "logs": "",
                "relay_endpoint": "relay://buyer-runtime-session/13",
                "connect_code": "abc123",
                "created_at": "2026-03-25T00:00:00Z",
                "expires_at": "2026-03-25T01:00:00Z",
                "ended_at": None,
            }
        },
    )
    monkeypatch.setattr(
        agent_server,
        "renew_backend_runtime_session",
        lambda **kwargs: {
            "session_id": kwargs["session_id"],
            "status": "running",
            "expires_at": "2026-03-25T01:30:00Z",
        },
    )

    client = TestClient(agent_server.app)
    response = client.post("/api/runtime/sessions/local-1/renew", json={"additional_minutes": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["expires_at"] == "2026-03-25T01:30:00Z"
    assert payload["renew_result"]["status"] == "running"
