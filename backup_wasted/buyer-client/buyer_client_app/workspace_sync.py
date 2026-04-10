from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import httpx

from buyer_client_app.errors import LocalAppError


def package_workspace(source_path: Path, archive_name: str = "workspace.zip") -> Path:
    if not source_path.exists() or not source_path.is_dir():
        raise LocalAppError(
            step="workspace.select",
            code="workspace_path_invalid",
            message="The selected workspace path does not exist or is not a directory.",
            hint="Choose a valid local folder before syncing to the buyer runtime.",
            details={"path": str(source_path)},
            status_code=422,
        )
    temp_dir = Path(tempfile.mkdtemp(prefix="pivot-buyer-workspace-"))
    archive_path = temp_dir / archive_name
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_path.rglob("*"):
            if path.is_file():
                archive.write(path, arcname=str(path.relative_to(source_path)))
    return archive_path


def sync_workspace(archive_path: Path, upload_url: str, extract_url: str) -> dict:
    if not archive_path.exists():
        raise LocalAppError(
            step="workspace.sync",
            code="workspace_archive_missing",
            message="The packaged workspace archive does not exist.",
            hint="Package the local workspace before trying to sync it.",
            details={"archive_path": str(archive_path)},
            status_code=409,
        )
    try:
        with httpx.Client(timeout=300.0, trust_env=False) as client:
            upload_response = client.post(
                upload_url,
                content=archive_path.read_bytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            upload_response.raise_for_status()
            upload_payload = upload_response.json()
            extract_response = client.post(extract_url, json={"archive_path": upload_payload["archive_path"]})
            extract_response.raise_for_status()
            extract_payload = extract_response.json()
    except httpx.HTTPError as exc:
        raise LocalAppError(
            step="workspace.sync",
            code="workspace_sync_failed",
            message="Failed to upload or extract the local workspace into the buyer runtime.",
            hint="Confirm the WireGuard tunnel is active and the runtime workspace sync endpoint is reachable.",
            details={"upload_url": upload_url, "extract_url": extract_url, "exception": str(exc)},
            status_code=502,
        ) from exc
    return {"upload": upload_payload, "extract": extract_payload}
