from __future__ import annotations

import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

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
                archive.write(path, arcname=path.relative_to(source_path).as_posix())
    return archive_path


def sync_workspace(
    archive_path: Path,
    *,
    upload_url: str,
    extract_url: str,
    status_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
    upload_attempts: int = 3,
) -> dict[str, Any]:
    if not archive_path.exists():
        raise LocalAppError(
            step="workspace.sync",
            code="workspace_archive_missing",
            message="The packaged workspace archive does not exist.",
            hint="Package the local workspace before syncing it to the buyer runtime.",
            details={"archive_path": str(archive_path)},
            status_code=409,
        )
    try:
        archive_bytes = archive_path.read_bytes()
        with httpx.Client(timeout=300.0, trust_env=False, transport=transport) as client:
            upload_response = _request_with_retry(
                client=client,
                method="POST",
                url=upload_url,
                attempts=upload_attempts,
                content=archive_bytes,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(len(archive_bytes)),
                    "Connection": "close",
                },
            )
            upload_response.raise_for_status()
            upload_payload = upload_response.json()

            extract_response = _request_with_retry(
                client=client,
                method="POST",
                url=extract_url,
                attempts=2,
                json={"archive_path": upload_payload["archive_path"]},
            )
            extract_response.raise_for_status()
            extract_payload = extract_response.json()

            status_payload: dict[str, Any] | None = None
            if status_url:
                status_response = _request_with_retry(
                    client=client,
                    method="GET",
                    url=status_url,
                    attempts=2,
                )
                status_response.raise_for_status()
                status_payload = status_response.json()
    except httpx.HTTPError as exc:
        raise LocalAppError(
            step="workspace.sync",
            code="workspace_sync_failed",
            message="Failed to upload or extract the local workspace into the buyer runtime.",
            hint="Confirm the WireGuard tunnel is active and the runtime workspace endpoints are reachable.",
            details={
                "upload_url": upload_url,
                "extract_url": extract_url,
                "status_url": status_url,
                "exception": str(exc),
            },
            status_code=502,
        ) from exc
    return {
        "archive_path": str(archive_path),
        "upload": upload_payload,
        "extract": extract_payload,
        "status": status_payload,
    }


def fetch_workspace_status(status_url: str) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            response = client.get(status_url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise LocalAppError(
            step="workspace.status",
            code="workspace_status_failed",
            message="Failed to read the runtime workspace status.",
            hint="Confirm the buyer runtime shell agent is reachable over WireGuard.",
            details={"status_url": status_url, "exception": str(exc)},
            status_code=502,
        ) from exc
    if not isinstance(payload, dict):
        raise LocalAppError(
            step="workspace.status",
            code="workspace_status_invalid",
            message="Runtime workspace status returned an invalid response payload.",
            hint="Refresh the runtime session and retry after the gateway is healthy.",
            details={"status_url": status_url},
            status_code=502,
        )
    return payload


def _request_with_retry(
    *,
    client: httpx.Client,
    method: str,
    url: str,
    attempts: int,
    headers: dict[str, str] | None = None,
    content: bytes | None = None,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    last_exc: httpx.HTTPError | None = None
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            return client.request(
                method,
                url,
                headers=headers,
                content=content,
                json=json,
            )
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadError,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
            httpx.WriteError,
            httpx.WriteTimeout,
        ) as exc:
            last_exc = exc
            if attempt >= attempts:
                raise
            time.sleep(min(0.5 * attempt, 1.5))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable")
