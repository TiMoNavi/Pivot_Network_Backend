from fastapi.testclient import TestClient

from app.core.config import settings


def test_health_endpoint_returns_minimal_service_status(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": settings.PROJECT_NAME,
    }
