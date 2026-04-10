from fastapi.testclient import TestClient

from seller_client_app.main import app


def test_window_session_open_heartbeat_close() -> None:
    client = TestClient(app)

    opened = client.post("/local-api/window-session/open")
    assert opened.status_code == 200, opened.text
    payload = opened.json()
    session_id = payload["session_id"]
    assert payload["status"] == "active"

    heartbeat = client.post("/local-api/window-session/heartbeat", headers={"X-Window-Session-Id": session_id})
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["session_id"] == session_id

    closed = client.post(f"/local-api/window-session/close?session_id={session_id}")
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"


def test_assistant_requires_window_session() -> None:
    client = TestClient(app)
    response = client.post("/local-api/assistant/message", json={"message": "sell my compute"})
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "window_session_missing"
