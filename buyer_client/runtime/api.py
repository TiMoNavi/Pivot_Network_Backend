from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "ok": True,
                "status": response.status,
                "data": json.loads(response.read().decode("utf-8")),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return {"ok": False, "status": exc.code, "data": parsed}


def login_or_register(backend_url: str, email: str, password: str, display_name: str | None = None) -> dict[str, Any]:
    register = request_json(
        "POST",
        f"{backend_url.rstrip('/')}/api/v1/auth/register",
        {"email": email, "password": password, "display_name": display_name},
    )
    if not register["ok"] and register["status"] != 409:
        raise RuntimeError(f"register_failed: {register['data']}")

    login = request_json(
        "POST",
        f"{backend_url.rstrip('/')}/api/v1/auth/login",
        {"email": email, "password": password},
    )
    if not login["ok"]:
        raise RuntimeError(f"login_failed: {login['data']}")
    return {
        "access_token": str(login["data"]["access_token"]),
        "user": login["data"]["user"],
        "register_result": register,
        "login_result": login,
    }


def create_runtime_session(
    *,
    backend_url: str,
    email: str,
    password: str,
    seller_node_key: str = "",
    offer_id: int | None = None,
    code_filename: str,
    code_content: str,
    runtime_image: str = "python:3.12-alpine",
    requested_duration_minutes: int = 30,
    session_mode: str = "code_run",
    source_type: str = "inline_code",
    entry_command: list[str] | None = None,
    archive_filename: str | None = None,
    archive_content_base64: str = "",
    source_ref: str | None = None,
    working_dir: str | None = None,
    run_command: list[str] | None = None,
) -> dict[str, Any]:
    auth = login_or_register(backend_url, email, password, display_name="Buyer Agent")
    buyer_token = auth["access_token"]

    create = request_json(
        "POST",
        f"{backend_url.rstrip('/')}/api/v1/buyer/runtime-sessions",
        {
            "seller_node_key": seller_node_key or None,
            "offer_id": offer_id,
            "session_mode": session_mode,
            "source_type": source_type,
            "runtime_image": runtime_image,
            "code_filename": code_filename,
            "code_content": code_content,
            "archive_filename": archive_filename,
            "archive_content_base64": archive_content_base64,
            "source_ref": source_ref,
            "working_dir": working_dir,
            "run_command": run_command,
            "requested_duration_minutes": requested_duration_minutes,
            "entry_command": entry_command,
        },
        token=buyer_token,
        timeout=120,
    )
    if not create["ok"]:
        raise RuntimeError(f"create_runtime_session_failed: {create['data']}")

    connect_code = str(create["data"]["connect_code"])
    redeem = request_json(
        "POST",
        f"{backend_url.rstrip('/')}/api/v1/buyer/runtime-sessions/redeem",
        {"connect_code": connect_code},
    )
    if not redeem["ok"]:
        raise RuntimeError(f"redeem_connect_code_failed: {redeem['data']}")

    return {
        "backend_url": backend_url,
        "buyer_email": email,
        "buyer_token": buyer_token,
        "session_id": int(create["data"]["session_id"]),
        "offer_id": create["data"].get("offer_id"),
        "seller_node_key": str(create["data"]["seller_node_key"]),
        "runtime_image": str(create["data"]["runtime_image"]),
        "code_filename": code_filename,
        "session_mode": session_mode,
        "source_type": source_type,
        "connect_code": connect_code,
        "session_token": str(redeem["data"]["session_token"]),
        "relay_endpoint": str(redeem["data"]["relay_endpoint"]),
        "create_result": create,
        "redeem_result": redeem,
        "auth": auth,
    }


def read_runtime_session(*, backend_url: str, buyer_token: str, session_id: int) -> dict[str, Any]:
    response = request_json(
        "GET",
        f"{backend_url.rstrip('/')}/api/v1/buyer/runtime-sessions/{session_id}",
        token=buyer_token,
        timeout=120,
    )
    if not response["ok"]:
        raise RuntimeError(f"read_runtime_session_failed: {response['data']}")
    return response["data"]


def wait_for_runtime_completion(
    *,
    backend_url: str,
    buyer_token: str,
    session_id: int,
    poll_seconds: int = 2,
    timeout_seconds: int = 300,
    require_logs: bool = False,
    log_grace_polls: int = 5,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    terminal_without_logs_polls = 0
    while time.time() < deadline:
        payload = read_runtime_session(backend_url=backend_url, buyer_token=buyer_token, session_id=session_id)
        if on_update is not None:
            on_update(payload)
        if payload.get("status") in {"completed", "failed", "stopped"}:
            if require_logs and not (payload.get("logs") or ""):
                terminal_without_logs_polls += 1
                if terminal_without_logs_polls <= log_grace_polls:
                    time.sleep(poll_seconds)
                    continue
            return payload
        time.sleep(poll_seconds)
    raise RuntimeError("wait_for_runtime_completion_timeout")


def stop_runtime_session(*, backend_url: str, buyer_token: str, session_id: int) -> dict[str, Any]:
    response = request_json(
        "POST",
        f"{backend_url.rstrip('/')}/api/v1/buyer/runtime-sessions/{session_id}/stop",
        token=buyer_token,
        timeout=120,
    )
    if not response["ok"]:
        raise RuntimeError(f"stop_runtime_session_failed: {response['data']}")
    return response["data"]


def renew_runtime_session(*, backend_url: str, buyer_token: str, session_id: int, additional_minutes: int) -> dict[str, Any]:
    response = request_json(
        "POST",
        f"{backend_url.rstrip('/')}/api/v1/buyer/runtime-sessions/{session_id}/renew",
        {"additional_minutes": additional_minutes},
        token=buyer_token,
        timeout=120,
    )
    if not response["ok"]:
        raise RuntimeError(f"renew_runtime_session_failed: {response['data']}")
    return response["data"]


def stop_session(*, backend_url: str, email: str, password: str, session_id: int) -> dict[str, Any]:
    auth = login_or_register(backend_url, email, password, display_name="Buyer Agent")
    return stop_runtime_session(
        backend_url=backend_url,
        buyer_token=auth["access_token"],
        session_id=session_id,
    )
