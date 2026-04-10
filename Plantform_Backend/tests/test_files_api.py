from pathlib import Path

from fastapi.testclient import TestClient

from backend_app.api.deps import get_file_service
from backend_app.main import app
from backend_app.services.file_service import FileService


def test_files_endpoints(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / "seller-bootstrap-example.txt"
    target.write_text("hello seller\n", encoding="utf-8")

    app.dependency_overrides[get_file_service] = lambda: FileService(downloads)
    client = TestClient(app)

    listing = client.get("/api/v1/files/")
    assert listing.status_code == 200, listing.text
    payload = listing.json()
    assert payload["total"] == 1
    assert payload["items"][0]["relative_path"] == "seller-bootstrap-example.txt"

    download = client.get("/api/v1/files/download/seller-bootstrap-example.txt")
    assert download.status_code == 200, download.text
    assert download.text == "hello seller\n"

    missing = client.get("/api/v1/files/download/not-found.txt")
    assert missing.status_code == 404

    traversal = client.get("/api/v1/files/download/../secrets.txt")
    assert traversal.status_code == 404

    app.dependency_overrides.clear()
