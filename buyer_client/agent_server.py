from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buyer_client.agent_cli import (
    bootstrap_runtime_session_wireguard,
    create_runtime_session,
    disconnect_runtime_session_wireguard,
    exec_runtime_command_locally,
    read_runtime_session,
    renew_runtime_session as renew_backend_runtime_session,
    run_archive,
    run_github_repo,
    start_shell_session,
    stop_runtime_session,
)
from seller_client.agent_mcp import wireguard_summary

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = str(REPO_ROOT / ".cache" / "buyer-web")
INDEX_HTML = REPO_ROOT / "buyer_client" / "web" / "index.html"

SESSION_STORE: dict[str, dict[str, Any]] = {}
TERMINAL_SESSION_STATES = {"completed", "failed", "stopped", "expired"}


class RunCodeRequest(BaseModel):
    backend_url: str = "http://127.0.0.1:8000"
    email: str
    password: str
    seller_node_key: str
    runtime_image: str = "python:3.12-alpine"
    code_filename: str = "main.py"
    code_content: str = Field(min_length=1, max_length=200_000)
    requested_duration_minutes: int = Field(default=30, ge=1, le=720)
    state_dir: str | None = None


class RunArchiveRequest(BaseModel):
    backend_url: str = "http://127.0.0.1:8000"
    email: str
    password: str
    seller_node_key: str
    source_path: str
    runtime_image: str = "python:3.12-alpine"
    working_dir: str | None = None
    run_command: str = ""
    requested_duration_minutes: int = Field(default=30, ge=1, le=720)
    state_dir: str | None = None


class RunGitHubRequest(BaseModel):
    backend_url: str = "http://127.0.0.1:8000"
    email: str
    password: str
    seller_node_key: str
    repo_url: str
    repo_ref: str = "main"
    runtime_image: str = "python:3.12-alpine"
    working_dir: str | None = None
    run_command: str = ""
    requested_duration_minutes: int = Field(default=30, ge=1, le=720)
    state_dir: str | None = None


class StartShellRequest(BaseModel):
    backend_url: str = "http://127.0.0.1:8000"
    email: str
    password: str
    seller_node_key: str
    runtime_image: str = "python:3.12-alpine"
    requested_duration_minutes: int = Field(default=30, ge=1, le=720)
    state_dir: str | None = None


class ExecRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    state_dir: str | None = None


class StopSessionRequest(BaseModel):
    state_dir: str | None = None


class RenewSessionRequest(BaseModel):
    additional_minutes: int = Field(default=30, ge=1, le=720)
    state_dir: str | None = None


class WireGuardRequest(BaseModel):
    state_dir: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir(provided: str | None) -> Path:
    return Path(provided or DEFAULT_STATE_DIR).expanduser().resolve()


def _activity_path(state_dir: str | None) -> Path:
    root = _state_dir(state_dir)
    path = root / "logs" / "buyer-web-actions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_activity(state_dir: str | None, entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entry)
    payload["timestamp"] = _utc_now_iso()
    path = _activity_path(state_dir)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return payload


def _read_activity(state_dir: str | None, limit: int = 20) -> list[dict[str, Any]]:
    path = _activity_path(state_dir)
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(items) >= limit:
            break
    return items


def _session_state_dir(record: dict[str, Any]) -> str:
    return str(_state_dir(record.get("state_dir")))


def _wireguard_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "wireguard_status": record.get("wireguard_status", ""),
        "wireguard_interface": record.get("wireguard_interface", ""),
        "wireguard_client_address": record.get("wireguard_client_address", ""),
        "seller_wireguard_target": record.get("seller_wireguard_target", ""),
        "wireguard_last_bootstrap_at": record.get("wireguard_last_bootstrap_at", ""),
        "wireguard_activation_mode": record.get("wireguard_activation_mode", ""),
    }


def _compose_session_logs(record: dict[str, Any], remote_logs: str | None) -> str:
    parts = []
    remote = (remote_logs or "").strip()
    local_exec = (record.get("local_exec_history") or "").strip()
    if remote:
        parts.append(remote)
    if local_exec:
        parts.append(local_exec)
    return "\n\n".join(parts)


def _masked_session(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "local_id": record["local_id"],
        "backend_url": record["backend_url"],
        "buyer_email": record["buyer_email"],
        "session_id": record["session_id"],
        "seller_node_key": record["seller_node_key"],
        "runtime_image": record["runtime_image"],
        "code_filename": record["code_filename"],
        "session_mode": record.get("session_mode", "code_run"),
        "network_mode": record.get("network_mode", "wireguard"),
        "status": record.get("status", ""),
        "service_name": record.get("service_name", ""),
        "relay_endpoint": record.get("relay_endpoint", ""),
        "logs": record.get("logs", ""),
        "connect_code": record.get("connect_code", ""),
        "created_at": record.get("created_at", ""),
        "expires_at": record.get("expires_at"),
        "ended_at": record.get("ended_at"),
        **_wireguard_fields(record),
    }


def _record_from_created_session(
    *,
    local_id: str,
    payload: BaseModel,
    session: dict[str, Any],
    code_filename: str,
    session_mode: str,
) -> dict[str, Any]:
    create_data = session.get("create_result", {}).get("data", {})
    redeem_data = session.get("redeem_result", {}).get("data", {})
    return {
        "local_id": local_id,
        "state_dir": str(_state_dir(getattr(payload, "state_dir", None))),
        "backend_url": payload.backend_url,
        "buyer_email": payload.email,
        "buyer_token": session["buyer_token"],
        "session_id": session["session_id"],
        "seller_node_key": payload.seller_node_key,
        "runtime_image": payload.runtime_image,
        "code_filename": code_filename,
        "session_mode": session_mode,
        "network_mode": redeem_data.get("network_mode", "wireguard"),
        "status": redeem_data.get("status", "created"),
        "service_name": "",
        "logs": "",
        "relay_endpoint": session["relay_endpoint"],
        "connect_code": session["connect_code"],
        "created_at": _utc_now_iso(),
        "expires_at": create_data.get("expires_at"),
        "ended_at": None,
        "remote_logs": "",
        "local_exec_history": "",
        "wireguard_status": "",
        "wireguard_interface": "wg-buyer",
        "wireguard_client_address": "",
        "seller_wireguard_target": "",
        "wireguard_last_bootstrap_at": "",
        "wireguard_activation_mode": "",
    }


def _deactivate_local_wireguard(record: dict[str, Any]) -> dict[str, Any]:
    interface_name = record.get("wireguard_interface") or "wg-buyer"
    result = disconnect_runtime_session_wireguard(
        state_dir=_session_state_dir(record),
        interface_name=interface_name,
    )
    if result.get("ok"):
        record["wireguard_status"] = "disconnected"
        record["wireguard_activation_mode"] = "disconnected"
    return result


def _deactivate_other_wireguard_sessions(target_local_id: str, state_dir: str) -> None:
    for local_id, record in SESSION_STORE.items():
        if local_id == target_local_id:
            continue
        if _session_state_dir(record) != state_dir:
            continue
        if record.get("wireguard_status") != "active":
            continue
        _deactivate_local_wireguard(record)


def _refresh_session(local_id: str) -> dict[str, Any]:
    record = SESSION_STORE.get(local_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Local buyer session not found.")

    payload = read_runtime_session(
        backend_url=record["backend_url"],
        buyer_token=record["buyer_token"],
        session_id=record["session_id"],
    )
    remote_logs = payload.get("logs", "")
    record["status"] = payload.get("status", "")
    record["service_name"] = payload.get("service_name", "")
    record["remote_logs"] = remote_logs
    record["logs"] = _compose_session_logs(record, remote_logs)
    record["ended_at"] = payload.get("ended_at")
    record["expires_at"] = payload.get("expires_at")
    record["network_mode"] = payload.get("network_mode", record.get("network_mode", "wireguard"))
    record["wireguard_client_address"] = payload.get("buyer_wireguard_client_address") or record.get(
        "wireguard_client_address", ""
    )
    record["seller_wireguard_target"] = payload.get("seller_wireguard_target") or record.get(
        "seller_wireguard_target", ""
    )

    if record["status"] in {"stopped", "expired"} and record.get("wireguard_status") == "active":
        _deactivate_local_wireguard(record)

    return _masked_session(record)


def _dashboard_payload(state_dir: str | None) -> dict[str, Any]:
    resolved_state_dir = str(_state_dir(state_dir))
    sessions = [
        _masked_session(record)
        for record in reversed(list(SESSION_STORE.values()))
        if _session_state_dir(record) == resolved_state_dir
    ]
    return {
        "ok": True,
        "state_dir": resolved_state_dir,
        "summary": {
            "session_count": len(sessions),
            "running_count": sum(1 for item in sessions if item["status"] == "running"),
            "completed_count": sum(1 for item in sessions if item["status"] == "completed"),
            "wireguard_active_count": sum(1 for item in sessions if item["wireguard_status"] == "active"),
        },
        "sessions": sessions,
        "local_activity": _read_activity(state_dir),
    }


app = FastAPI(title="Pivot Buyer Local Web")


@app.get("/", response_class=HTMLResponse)
def read_index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.get("/api/health")
def read_health() -> dict[str, Any]:
    return {"status": "ok", "service": "buyer-agent-web"}


@app.get("/api/dashboard")
def read_dashboard(state_dir: str | None = None) -> dict[str, Any]:
    return _dashboard_payload(state_dir)


@app.post("/api/runtime/run-code")
def run_code(payload: RunCodeRequest) -> JSONResponse:
    session = create_runtime_session(
        backend_url=payload.backend_url,
        email=payload.email,
        password=payload.password,
        seller_node_key=payload.seller_node_key,
        code_filename=payload.code_filename,
        code_content=payload.code_content,
        runtime_image=payload.runtime_image,
        requested_duration_minutes=payload.requested_duration_minutes,
    )
    local_id = uuid.uuid4().hex
    record = _record_from_created_session(
        local_id=local_id,
        payload=payload,
        session=session,
        code_filename=payload.code_filename,
        session_mode="code_run",
    )
    SESSION_STORE[local_id] = record
    activity = _append_activity(
        payload.state_dir,
        {
            "action": "run_code",
            "status": "success",
            "title": "Create buyer runtime session",
            "summary": f"Created session {session['session_id']} on seller node {payload.seller_node_key}.",
        },
    )
    return JSONResponse(
        {
            "ok": True,
            "action": "run_code",
            "status": "success",
            "session": _masked_session(record),
            "activity_entry": activity,
        }
    )


@app.post("/api/runtime/run-archive")
def run_archive_endpoint(payload: RunArchiveRequest) -> JSONResponse:
    final_payload = run_archive(
        backend_url=payload.backend_url,
        email=payload.email,
        password=payload.password,
        seller_node_key=payload.seller_node_key,
        source_path=Path(payload.source_path),
        runtime_image=payload.runtime_image,
        poll_seconds=2,
        working_dir=payload.working_dir,
        run_command=["sh", "-lc", payload.run_command] if payload.run_command else None,
        requested_duration_minutes=payload.requested_duration_minutes,
    )
    activity = _append_activity(
        payload.state_dir,
        {
            "action": "run_archive",
            "status": "success",
            "title": "Create archive runtime session",
            "summary": f"Ran archive source on seller node {payload.seller_node_key}.",
        },
    )
    return JSONResponse(
        {
            "ok": True,
            "action": "run_archive",
            "status": "success",
            "result": final_payload,
            "activity_entry": activity,
        }
    )


@app.post("/api/runtime/run-github")
def run_github_endpoint(payload: RunGitHubRequest) -> JSONResponse:
    final_payload = run_github_repo(
        backend_url=payload.backend_url,
        email=payload.email,
        password=payload.password,
        seller_node_key=payload.seller_node_key,
        repo_url=payload.repo_url,
        repo_ref=payload.repo_ref,
        runtime_image=payload.runtime_image,
        poll_seconds=2,
        working_dir=payload.working_dir,
        run_command=["sh", "-lc", payload.run_command] if payload.run_command else None,
        requested_duration_minutes=payload.requested_duration_minutes,
    )
    activity = _append_activity(
        payload.state_dir,
        {
            "action": "run_github",
            "status": "success",
            "title": "Create GitHub runtime session",
            "summary": f"Ran GitHub source {payload.repo_url}@{payload.repo_ref}.",
        },
    )
    return JSONResponse(
        {
            "ok": True,
            "action": "run_github",
            "status": "success",
            "result": final_payload,
            "activity_entry": activity,
        }
    )


@app.post("/api/runtime/start-shell")
def start_shell(payload: StartShellRequest) -> JSONResponse:
    session = start_shell_session(
        backend_url=payload.backend_url,
        email=payload.email,
        password=payload.password,
        seller_node_key=payload.seller_node_key,
        runtime_image=payload.runtime_image,
        requested_duration_minutes=payload.requested_duration_minutes,
    )
    local_id = uuid.uuid4().hex
    record = _record_from_created_session(
        local_id=local_id,
        payload=payload,
        session=session,
        code_filename="__shell__",
        session_mode="shell",
    )
    SESSION_STORE[local_id] = record
    activity = _append_activity(
        payload.state_dir,
        {
            "action": "start_shell",
            "status": "success",
            "title": "Create buyer shell session",
            "summary": f"Created shell session {session['session_id']} on seller node {payload.seller_node_key}.",
        },
    )
    return JSONResponse(
        {
            "ok": True,
            "action": "start_shell",
            "status": "success",
            "session": _masked_session(record),
            "activity_entry": activity,
        }
    )


@app.get("/api/runtime/sessions/{local_id}")
def read_runtime_session_status(local_id: str) -> JSONResponse:
    payload = _refresh_session(local_id)
    return JSONResponse({"ok": True, "session": payload})


@app.post("/api/runtime/sessions/{local_id}/wireguard/bootstrap")
def bootstrap_runtime_session_wireguard_endpoint(local_id: str, payload: WireGuardRequest) -> JSONResponse:
    record = SESSION_STORE.get(local_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Local buyer session not found.")

    state_dir = str(_state_dir(payload.state_dir or record.get("state_dir")))
    record["state_dir"] = state_dir
    _deactivate_other_wireguard_sessions(local_id, state_dir)

    result = bootstrap_runtime_session_wireguard(
        backend_url=record["backend_url"],
        buyer_token=record["buyer_token"],
        session_id=record["session_id"],
        state_dir=state_dir,
    )
    bundle = result.get("bundle", {})
    activation_result = result.get("activation_result", {})
    record["network_mode"] = "wireguard"
    record["wireguard_interface"] = bundle.get("interface_name", "wg-buyer")
    record["wireguard_client_address"] = bundle.get("client_address", "")
    record["seller_wireguard_target"] = bundle.get("seller_wireguard_target", "") or ""
    record["wireguard_last_bootstrap_at"] = _utc_now_iso()
    record["wireguard_activation_mode"] = str(activation_result.get("mode") or "direct")
    record["wireguard_status"] = "active" if activation_result.get("ok") else "activation_failed"
    wg_state = wireguard_summary(interface_name=record["wireguard_interface"], state_dir=state_dir)
    activity = _append_activity(
        state_dir,
        {
            "action": "wireguard_bootstrap",
            "status": "success" if activation_result.get("ok") else "error",
            "title": "Bootstrap buyer WireGuard lease",
            "summary": (
                f"Session {record['session_id']} lease credentials issued. "
                f"seller={record['seller_wireguard_target'] or 'unknown'} "
                f"buyer={record['wireguard_client_address'] or 'unknown'}"
            ),
        },
    )
    return JSONResponse(
        {
            "ok": bool(activation_result.get("ok")),
            "session": _masked_session(record),
            "wireguard_result": result,
            "wireguard_state": wg_state,
            "activity_entry": activity,
        }
    )


@app.post("/api/runtime/sessions/{local_id}/wireguard/disconnect")
def disconnect_runtime_session_wireguard_endpoint(local_id: str, payload: WireGuardRequest) -> JSONResponse:
    record = SESSION_STORE.get(local_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Local buyer session not found.")

    state_dir = str(_state_dir(payload.state_dir or record.get("state_dir")))
    record["state_dir"] = state_dir
    result = disconnect_runtime_session_wireguard(
        state_dir=state_dir,
        interface_name=record.get("wireguard_interface") or "wg-buyer",
    )
    if result.get("ok"):
        record["wireguard_status"] = "disconnected"
        record["wireguard_activation_mode"] = "disconnected"
    wg_state = wireguard_summary(interface_name=record.get("wireguard_interface") or "wg-buyer", state_dir=state_dir)
    activity = _append_activity(
        state_dir,
        {
            "action": "wireguard_disconnect",
            "status": "success" if result.get("ok") else "error",
            "title": "Disconnect buyer WireGuard lease",
            "summary": f"Local interface {(record.get('wireguard_interface') or 'wg-buyer')} disconnected.",
        },
    )
    return JSONResponse(
        {
            "ok": bool(result.get("ok")),
            "session": _masked_session(record),
            "disconnect_result": result,
            "wireguard_state": wg_state,
            "activity_entry": activity,
        }
    )


@app.post("/api/runtime/sessions/{local_id}/renew")
def renew_runtime_session_endpoint(local_id: str, payload: RenewSessionRequest) -> JSONResponse:
    record = SESSION_STORE.get(local_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Local buyer session not found.")
    result = renew_backend_runtime_session(
        backend_url=record["backend_url"],
        buyer_token=record["buyer_token"],
        session_id=record["session_id"],
        additional_minutes=payload.additional_minutes,
    )
    record["expires_at"] = result.get("expires_at")
    activity = _append_activity(
        payload.state_dir or record.get("state_dir"),
        {
            "action": "renew_session",
            "status": "success",
            "title": "Renew buyer runtime lease",
            "summary": f"Session {record['session_id']} extended by {payload.additional_minutes} minutes.",
        },
    )
    return JSONResponse(
        {
            "ok": True,
            "session": _masked_session(record),
            "renew_result": result,
            "activity_entry": activity,
        }
    )


@app.post("/api/runtime/sessions/{local_id}/exec")
def exec_runtime_session(local_id: str, payload: ExecRequest) -> JSONResponse:
    record = SESSION_STORE.get(local_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Local buyer session not found.")
    service_name = record.get("service_name") or f"buyer-runtime-session-{record['session_id']}"
    refreshed = _refresh_session(local_id)
    service_name = refreshed.get("service_name") or service_name
    exec_result = exec_runtime_command_locally(service_name, payload.command)
    transcript = (
        f"$ {payload.command}\n"
        f"{exec_result.get('stdout') or ''}"
        f"{exec_result.get('stderr') or ''}"
    )
    existing_local_exec = (record.get("local_exec_history") or "").strip()
    record["local_exec_history"] = (
        f"{existing_local_exec}\n\n{transcript}".strip() if existing_local_exec else transcript.strip()
    )
    record["logs"] = _compose_session_logs(record, record.get("remote_logs") or "")
    activity = _append_activity(
        payload.state_dir or record.get("state_dir"),
        {
            "action": "exec",
            "status": "success" if exec_result.get("ok") else "error",
            "title": "Exec inside runtime container",
            "summary": f"Session {record['session_id']} exec: {payload.command}",
        },
    )
    return JSONResponse(
        {
            "ok": bool(exec_result.get("ok")),
            "session": _masked_session(record),
            "exec_result": exec_result,
            "activity_entry": activity,
        }
    )


@app.post("/api/runtime/sessions/{local_id}/stop")
def stop_runtime_session_endpoint(local_id: str, payload: StopSessionRequest) -> JSONResponse:
    record = SESSION_STORE.get(local_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Local buyer session not found.")

    if record.get("wireguard_status") == "active":
        _deactivate_local_wireguard(record)

    stop_runtime_session(
        backend_url=record["backend_url"],
        buyer_token=record["buyer_token"],
        session_id=record["session_id"],
    )
    record["status"] = "stopped"
    record["ended_at"] = _utc_now_iso()
    activity = _append_activity(
        payload.state_dir or record.get("state_dir"),
        {
            "action": "stop_session",
            "status": "success",
            "title": "Stop buyer runtime session",
            "summary": f"Stopped session {record['session_id']}.",
        },
    )
    return JSONResponse({"ok": True, "session": _masked_session(record), "activity_entry": activity})


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=3857)


if __name__ == "__main__":
    main()
