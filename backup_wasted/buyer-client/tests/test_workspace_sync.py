from pathlib import Path

from buyer_client_app.workspace_sync import package_workspace


def test_package_workspace(tmp_path: Path) -> None:
    src = tmp_path / "workspace"
    src.mkdir()
    (src / "hello.txt").write_text("hello", encoding="utf-8")
    archive = package_workspace(src)
    assert archive.exists()
    assert archive.name.endswith(".zip")
