from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from buyer_client_app.backend import BackendClient, BackendClientError
from buyer_client_app.config import Settings
from buyer_client_app.errors import LocalAppError
from buyer_client_app.flow import build_runtime_access_plan
from buyer_client_app.state import BuyerClientState
from buyer_client_app.wireguard import (
    bring_down,
    bring_up,
    build_interface_name,
    generate_keypair,
    write_config,
)
from buyer_client_app.workspace import fetch_workspace_status, package_workspace, sync_workspace


def import_grant_code(state: BuyerClientState, grant_code: str) -> dict[str, Any]:
    cleaned = str(grant_code or "").strip()
    if len(cleaned) < 8:
        raise LocalAppError(
            step="grant.import",
            code="grant_code_invalid",
            message="Grant code is missing or too short.",
            hint="Paste the full grant code issued by the platform backend.",
            status_code=422,
        )
    state.set_imported_grant_code(cleaned)
    return {"status": "imported", "grant_code": cleaned}


def refresh_active_grants(
    *,
    state: BuyerClientState,
    backend_client: BackendClient,
) -> dict[str, Any]:
    try:
        response = backend_client.list_active_access_grants()
    except BackendClientError as exc:
        raise _backend_local_error(
            "access_grants.active",
            exc,
            message="Failed to refresh the buyer's active access grants.",
            hint="Retry after backend connectivity is restored.",
        ) from exc
    items = list(response.get("items") or [])
    state.set_active_access_grants(items)
    return {"items": items, "total": response.get("total", len(items))}


def create_runtime_session(
    *,
    settings: Settings,
    state: BuyerClientState,
    backend_client: BackendClient,
    grant_id: str | None = None,
    grant_code: str | None = None,
    network_mode: str = "wireguard",
) -> dict[str, Any]:
    resolved_grant_id = _optional_str(grant_id) or _optional_str((state.current_access_grant() or {}).get("id"))
    resolved_grant_code = _resolve_grant_code(state, grant_code)
    if not resolved_grant_id and not resolved_grant_code:
        raise LocalAppError(
            step="runtime_session.create",
            code="grant_missing",
            message="No access grant is selected for runtime session creation.",
            hint="Attach an active grant or import a grant code first.",
            status_code=409,
        )

    private_key, public_key = generate_keypair()
    try:
        if resolved_grant_id:
            runtime_session = backend_client.redeem_access_grant(
                resolved_grant_id,
                public_key,
                network_mode=network_mode,
            )
        else:
            runtime_session = backend_client.redeem_access_grant_by_code(
                resolved_grant_code or "",
                public_key,
                network_mode=network_mode,
            )
    except BackendClientError as exc:
        raise _backend_local_error(
            "runtime_session.create",
            exc,
            message="Failed to redeem the grant into a runtime session.",
            hint="Retry after the live runtime chain is healthy and the grant is still valid.",
        ) from exc

    runtime_session = _await_runtime_session_ready(
        backend_client=backend_client,
        runtime_session=runtime_session,
    )

    order, access_grant = _hydrate_runtime_context(
        state=state,
        backend_client=backend_client,
        runtime_session=runtime_session,
    )
    runtime_plan = build_runtime_access_plan(order, access_grant, runtime_session)

    if order is not None and access_grant is not None:
        state.set_activation(order, access_grant, runtime_plan)
    if resolved_grant_code:
        state.set_imported_grant_code(resolved_grant_code)
    state.set_runtime_session(
        runtime_session,
        runtime_plan=runtime_plan,
        wireguard_keypair={
            "private_key": private_key,
            "public_key": public_key,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    )

    return {
        "runtime_session": runtime_session,
        "runtime_access_plan": runtime_plan,
        "wireguard_public_key": public_key,
        "runtime_session_file": str(_session_paths(state).session_file),
    }


def refresh_runtime_session(
    *,
    state: BuyerClientState,
    backend_client: BackendClient,
    runtime_session_id: str | None = None,
) -> dict[str, Any]:
    current_runtime_session = state.current_runtime_session() or {}
    resolved_runtime_session_id = (
        _optional_str(runtime_session_id)
        or _optional_str(current_runtime_session.get("id"))
        or _optional_str((state.current_runtime_plan() or {}).get("runtime_session_id"))
    )
    if not resolved_runtime_session_id:
        raise LocalAppError(
            step="runtime_session.refresh",
            code="runtime_session_missing",
            message="Runtime session is not initialized.",
            hint="Create a runtime session before trying to refresh it.",
            status_code=409,
        )

    try:
        runtime_session = backend_client.get_runtime_session(resolved_runtime_session_id)
    except BackendClientError as exc:
        raise _backend_local_error(
            "runtime_session.refresh",
            exc,
            message="Failed to refresh the runtime session from the backend.",
            hint="Retry after the runtime bundle and backend API are reachable.",
        ) from exc

    order, access_grant = _hydrate_runtime_context(
        state=state,
        backend_client=backend_client,
        runtime_session=runtime_session,
    )
    runtime_plan = build_runtime_access_plan(order, access_grant, runtime_session)
    if order is not None and access_grant is not None:
        state.set_activation(order, access_grant, runtime_plan)
    state.set_runtime_session(runtime_session, runtime_plan=runtime_plan)
    return {
        "runtime_session": runtime_session,
        "runtime_access_plan": runtime_plan,
    }


def wireguard_up(
    *,
    settings: Settings,
    state: BuyerClientState,
) -> dict[str, Any]:
    runtime_plan = _require_runtime_plan(state)
    runtime_session = _require_runtime_session(state)
    keypair = state.current_wireguard_keypair() or {}
    private_key = _optional_str(keypair.get("private_key"))
    if not private_key:
        raise LocalAppError(
            step="wireguard.up",
            code="wireguard_keypair_missing",
            message="The local WireGuard keypair is missing.",
            hint="Create the runtime session again so the client can regenerate the keypair.",
            status_code=409,
        )

    paths = _session_paths(state)
    interface_name = build_interface_name(settings.wireguard_tunnel_prefix, runtime_session["id"])
    config_path = paths.wireguard_dir / f"{interface_name}.conf"
    write_config(
        config_path=config_path,
        private_key=private_key,
        profile=dict(runtime_plan.get("wireguard_profile") or {}),
    )
    result = bring_up(config_path)
    gateway_probe = _verify_runtime_gateway_readability(runtime_plan)
    if not gateway_probe["ok"]:
        try:
            bring_down(config_path)
        except LocalAppError:
            pass
        raise LocalAppError(
            step="wireguard.up",
            code="wireguard_gateway_unreachable",
            message="Buyer WireGuard tunnel came up, but the runtime gateway is not readable through it.",
            hint="Keep the same real chain fixed and inspect the Windows-local tunnel/data-plane boundary.",
            details={
                "config_path": str(config_path),
                "interface_name": result.get("interface_name"),
                "gateway_probe": gateway_probe,
            },
            status_code=502,
        )
    payload = {
        **result,
        "gateway_probe": gateway_probe,
        "runtime_session_id": runtime_session["id"],
        "started_at": datetime.now(UTC).isoformat(),
    }
    state.set_wireguard_state(payload)
    return payload


def wireguard_down(*, state: BuyerClientState) -> dict[str, Any]:
    runtime_session = _require_runtime_session(state)
    paths = _session_paths(state)
    current_state = state.current_wireguard_state() or {}
    interface_name = build_interface_name(state.settings.wireguard_tunnel_prefix, runtime_session["id"])
    config_path = Path(
        str(
            current_state.get("config_path")
            or paths.wireguard_dir / f"{interface_name}.conf"
        )
    )
    result = bring_down(config_path)
    payload = {
        **result,
        "runtime_session_id": runtime_session["id"],
        "stopped_at": datetime.now(UTC).isoformat(),
    }
    state.set_wireguard_state(payload)
    return payload


def open_shell(state: BuyerClientState) -> dict[str, Any]:
    runtime_plan = _require_runtime_plan(state)
    shell_embed_url = _optional_str(((runtime_plan.get("network_entry") or {}).get("shell_embed_url")))
    if not shell_embed_url:
        raise LocalAppError(
            step="runtime_shell.open",
            code="shell_url_missing",
            message="Runtime shell URL is not available for the current session.",
            hint="Refresh the runtime session after the runtime bundle is ready.",
            status_code=409,
        )
    return {
        "runtime_session_id": _optional_str(runtime_plan.get("runtime_session_id")),
        "shell_embed_url": shell_embed_url,
        "wireguard_state": state.current_wireguard_state(),
    }


def sync_workspace_selection(
    *,
    settings: Settings,
    state: BuyerClientState,
    source_path: str | Path | None,
) -> dict[str, Any]:
    runtime_plan = _require_runtime_plan(state)
    network_entry = dict(runtime_plan.get("network_entry") or {})
    upload_url = _optional_str(network_entry.get("workspace_sync_url"))
    extract_url = _optional_str(network_entry.get("workspace_extract_url"))
    status_url = _optional_str(network_entry.get("workspace_status_url"))
    if not upload_url or not extract_url:
        raise LocalAppError(
            step="workspace.sync",
            code="workspace_urls_missing",
            message="Runtime workspace endpoints are not available for the current session.",
            hint="Refresh the runtime session after the live bundle bootstrap is ready.",
            status_code=409,
        )

    resolved_source_path = Path(
        str(
            source_path
            or (state.current_workspace_selection() or {}).get("path")
            or _session_paths(state).workspace_dir
        )
    ).expanduser()
    archive_path = package_workspace(resolved_source_path, settings.workspace_archive_name)
    result = sync_workspace(
        archive_path,
        upload_url=upload_url,
        extract_url=extract_url,
        status_url=status_url,
    )
    state.set_workspace_selection(
        {
            "path": str(resolved_source_path),
            "archive_path": str(archive_path),
            "last_synced_at": datetime.now(UTC).isoformat(),
        }
    )
    return {
        "workspace_selection": state.current_workspace_selection(),
        **result,
    }


def read_workspace_status(state: BuyerClientState) -> dict[str, Any]:
    runtime_plan = _require_runtime_plan(state)
    status_url = _optional_str(((runtime_plan.get("network_entry") or {}).get("workspace_status_url")))
    if not status_url:
        raise LocalAppError(
            step="workspace.status",
            code="workspace_status_url_missing",
            message="Runtime workspace status URL is not available for the current session.",
            hint="Refresh the runtime session after the shell agent reports workspace bootstrap data.",
            status_code=409,
        )
    return fetch_workspace_status(status_url)


def submit_task_execution(
    *,
    state: BuyerClientState,
    command: str,
) -> dict[str, Any]:
    runtime_plan = _require_runtime_plan(state)
    runtime_session = _require_runtime_session(state)
    task_exec_url = _optional_str(((runtime_plan.get("network_entry") or {}).get("task_exec_url")))
    cleaned_command = str(command or "").strip()
    if not cleaned_command:
        raise LocalAppError(
            step="task.submit",
            code="task_command_missing",
            message="Task command is required.",
            hint="Provide the shell command to run in the buyer runtime session.",
            status_code=422,
        )
    if not task_exec_url:
        raise LocalAppError(
            step="task.submit",
            code="task_exec_url_missing",
            message="Runtime task execution endpoint is not available for the current session.",
            hint="Refresh the runtime session after the shell agent is reachable.",
            status_code=409,
        )

    try:
        with httpx.Client(timeout=180.0, trust_env=False) as client:
            response = client.post(
                task_exec_url,
                json={"command": cleaned_command},
            )
            response.raise_for_status()
            remote_payload = response.json()
    except httpx.HTTPError as exc:
        raise LocalAppError(
            step="task.submit",
            code="task_submit_failed",
            message="Failed to execute the task against the buyer runtime shell agent.",
            hint="Confirm the WireGuard tunnel is up and the runtime exec endpoint is reachable.",
            details={"task_exec_url": task_exec_url, "exception": str(exc)},
            status_code=502,
        ) from exc

    task_id = str(uuid.uuid4())
    completed_at = datetime.now(UTC).isoformat()
    paths = _session_paths(state)
    stdout_path = paths.logs_dir / f"{task_id}.stdout.log"
    stderr_path = paths.logs_dir / f"{task_id}.stderr.log"
    stdout_text = str(remote_payload.get("stdout") or "")
    stderr_text = str(remote_payload.get("stderr") or "")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")

    record = {
        "id": task_id,
        "runtime_session_id": runtime_session["id"],
        "command": cleaned_command,
        "status": "succeeded" if int(remote_payload.get("exit_code") or 0) == 0 else "failed",
        "submitted_at": completed_at,
        "completed_at": completed_at,
        "exit_code": remote_payload.get("exit_code"),
        "stdout_log_path": str(stdout_path),
        "stderr_log_path": str(stderr_path),
        "remote_result": remote_payload,
    }
    state.write_task_execution_record(task_id, record)
    state.record_task_execution(
        {
            "id": task_id,
            "command": cleaned_command,
            "status": record["status"],
            "completed_at": completed_at,
            "exit_code": record["exit_code"],
            "stdout_log_path": str(stdout_path),
            "stderr_log_path": str(stderr_path),
        }
    )
    return record


def tail_task_logs(
    *,
    state: BuyerClientState,
    task_id: str | None = None,
    max_chars: int = 4000,
) -> dict[str, Any]:
    history = state.task_execution_history()
    resolved_task_id = _optional_str(task_id) or _optional_str((history[-1] if history else {}).get("id"))
    if not resolved_task_id:
        raise LocalAppError(
            step="task.logs",
            code="task_history_empty",
            message="No task execution history exists for the current runtime session.",
            hint="Submit a task before trying to read its logs.",
            status_code=404,
        )
    record = state.read_task_execution(resolved_task_id)
    if record is None:
        raise LocalAppError(
            step="task.logs",
            code="task_record_missing",
            message="The requested task record could not be found on disk.",
            hint="Refresh the runtime task list and retry.",
            details={"task_id": resolved_task_id},
            status_code=404,
        )
    stdout_text = str((record.get("remote_result") or {}).get("stdout") or "")
    stderr_text = str((record.get("remote_result") or {}).get("stderr") or "")
    return {
        "task_id": resolved_task_id,
        "status": record.get("status"),
        "exit_code": record.get("exit_code"),
        "stdout_tail": stdout_text[-max_chars:],
        "stderr_tail": stderr_text[-max_chars:],
        "stdout_log_path": record.get("stdout_log_path"),
        "stderr_log_path": record.get("stderr_log_path"),
    }


def _backend_local_error(step: str, exc: BackendClientError, *, message: str, hint: str) -> LocalAppError:
    return LocalAppError(
        step=step,
        code="backend_request_failed",
        message=message,
        hint=hint,
        details={
            "status_code": exc.status_code,
            "detail": exc.detail,
            "payload": exc.payload,
        },
        status_code=exc.status_code,
    )


def _await_runtime_session_ready(
    *,
    backend_client: BackendClient,
    runtime_session: dict[str, Any],
    attempts: int = 20,
    interval_seconds: float = 2.0,
) -> dict[str, Any]:
    current = dict(runtime_session)
    session_id = _optional_str(current.get("id"))
    if not session_id:
        return current

    for attempt in range(max(attempts, 1)):
        status = _optional_str(current.get("status"))
        bundle = _optional_str(current.get("runtime_bundle_status"))
        if status == "ready" and bundle == "running":
            return current
        if attempt == attempts - 1:
            break
        time.sleep(interval_seconds)
        try:
            current = backend_client.get_runtime_session(session_id)
        except BackendClientError:
            continue

    raise LocalAppError(
        step="runtime_session.create",
        code="runtime_session_not_ready",
        message="Runtime session did not converge to ready/running in time.",
        hint="Keep the same real chain fixed, wait for runtime bundle convergence, and retry.",
        details={
            "runtime_session_id": session_id,
            "status": current.get("status"),
            "runtime_bundle_status": current.get("runtime_bundle_status"),
        },
        status_code=502,
    )


def _resolve_grant_code(state: BuyerClientState, grant_code: str | None) -> str | None:
    direct = _optional_str(grant_code)
    if direct:
        return direct
    imported = state.imported_grant_code()
    if imported:
        return imported
    current_grant = state.current_access_grant() or {}
    payload = current_grant.get("connect_material_payload") or {}
    return _optional_str(payload.get("grant_code"))


def _hydrate_runtime_context(
    *,
    state: BuyerClientState,
    backend_client: BackendClient,
    runtime_session: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    order: dict[str, Any] | None = state.current_order()
    access_grant: dict[str, Any] | None = state.current_access_grant()
    target_access_grant_id = _optional_str(runtime_session.get("access_grant_id"))
    target_order_id = _optional_str(runtime_session.get("order_id"))

    try:
        grants_payload = backend_client.list_active_access_grants()
        items = list(grants_payload.get("items") or [])
        state.set_active_access_grants(items)
        if target_access_grant_id:
            access_grant = next(
                (dict(item) for item in items if _optional_str(item.get("id")) == target_access_grant_id),
                access_grant,
            )
    except BackendClientError:
        pass

    if target_order_id:
        try:
            order = backend_client.get_order(target_order_id)
        except BackendClientError:
            pass

    return order, access_grant


def _require_runtime_plan(state: BuyerClientState) -> dict[str, Any]:
    runtime_plan = state.current_runtime_plan()
    if runtime_plan is None:
        raise LocalAppError(
            step="runtime_session",
            code="runtime_plan_missing",
            message="Runtime access plan is not initialized.",
            hint="Create or refresh the runtime session before using runtime actions.",
            status_code=409,
        )
    return runtime_plan


def _require_runtime_session(state: BuyerClientState) -> dict[str, Any]:
    runtime_session = state.current_runtime_session()
    if runtime_session is None:
        raise LocalAppError(
            step="runtime_session",
            code="runtime_session_missing",
            message="Runtime session is not initialized.",
            hint="Create or refresh the runtime session before using runtime actions.",
            status_code=409,
        )
    return runtime_session


def _session_paths(state: BuyerClientState):
    session_key = state.current_session_key()
    if not session_key:
        raise LocalAppError(
            step="runtime_session",
            code="runtime_session_missing",
            message="Runtime session paths are not available yet.",
            hint="Create or refresh the runtime session before using runtime actions.",
            status_code=409,
        )
    return state.session_paths(session_key)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _verify_runtime_gateway_readability(runtime_plan: dict[str, Any]) -> dict[str, Any]:
    health_url = _runtime_gateway_health_url(runtime_plan)
    if not health_url:
        return {
            "ok": False,
            "health_url": None,
            "reason": "wireguard_gateway_health_url_missing",
        }
    last_error: str | None = None
    for attempt in range(1, 4):
        try:
            with httpx.Client(timeout=8.0, trust_env=False) as client:
                response = client.get(health_url)
                response.raise_for_status()
                payload = response.json()
            return {
                "ok": True,
                "health_url": health_url,
                "status_code": response.status_code,
                "payload": payload,
                "attempt": attempt,
            }
        except (httpx.HTTPError, ValueError) as exc:
            last_error = str(exc)
    return {
        "ok": False,
        "health_url": health_url,
        "exception": last_error,
    }


def _runtime_gateway_health_url(runtime_plan: dict[str, Any]) -> str | None:
    network_entry = dict(runtime_plan.get("network_entry") or {})
    wireguard_gateway_access_url = _optional_str(network_entry.get("wireguard_gateway_access_url"))
    if wireguard_gateway_access_url:
        return urljoin(wireguard_gateway_access_url, "health")
    shell_embed_url = _optional_str(network_entry.get("shell_embed_url"))
    if shell_embed_url:
        return urljoin(shell_embed_url, "../health")
    workspace_status_url = _optional_str(network_entry.get("workspace_status_url"))
    if workspace_status_url:
        return urljoin(workspace_status_url, "../health")
    return None
