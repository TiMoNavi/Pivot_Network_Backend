from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.workspace import package_workspace, sync_workspace


class WorkspaceTests(unittest.TestCase):
    def test_package_workspace_uses_portable_zip_entry_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "workspace"
            nested = src / "nested"
            nested.mkdir(parents=True)
            (nested / "hello.txt").write_text("hello", encoding="utf-8")

            archive = package_workspace(src)

            with zipfile.ZipFile(archive, "r") as zipped:
                names = zipped.namelist()

        self.assertEqual(names, ["nested/hello.txt"])

    def test_sync_workspace_retries_remote_protocol_disconnect(self) -> None:
        upload_attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/workspace/upload":
                upload_attempts["count"] += 1
                if upload_attempts["count"] == 1:
                    raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
                return httpx.Response(200, json={"status": "uploaded", "archive_path": "/tmp/runtime-workspace.zip"})
            if request.url.path == "/api/workspace/extract":
                return httpx.Response(200, json={"status": "extracted", "workspace_root": "/workspace"})
            if request.url.path == "/api/workspace/status":
                return httpx.Response(200, json={"workspace_root": "/workspace", "files": [{"path": "README.txt"}]})
            raise AssertionError(f"unexpected request path: {request.url.path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "workspace"
            src.mkdir()
            (src / "README.txt").write_text("stage6", encoding="utf-8")
            archive = package_workspace(src)

            result = sync_workspace(
                archive,
                upload_url="http://10.66.66.1:32080/api/workspace/upload",
                extract_url="http://10.66.66.1:32080/api/workspace/extract",
                status_url="http://10.66.66.1:32080/api/workspace/status",
                transport=httpx.MockTransport(handler),
            )

        self.assertEqual(upload_attempts["count"], 2)
        self.assertEqual(result["upload"]["status"], "uploaded")
        self.assertEqual(result["extract"]["status"], "extracted")
        self.assertEqual(result["status"]["workspace_root"], "/workspace")


if __name__ == "__main__":
    unittest.main()
