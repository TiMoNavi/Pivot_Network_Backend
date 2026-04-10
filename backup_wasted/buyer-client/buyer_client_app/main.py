from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from buyer_client_app.backend import BackendClient, BackendClientError
from buyer_client_app.codex_session import cleanup_codex_session, prepare_codex_session, run_codex_assistant
from buyer_client_app.config import get_settings
from buyer_client_app.env_scan import scan_environment
from buyer_client_app.errors import LocalAppError
from buyer_client_app.state import BuyerClientState
from buyer_client_app.wireguard_client import generate_keypair, install_tunnel, remove_tunnel, write_config
from buyer_client_app.workspace_sync import package_workspace, sync_workspace

settings = get_settings()
state = BuyerClientState(settings)
app = FastAPI(title="Pivot Buyer Client", version="0.1.0")
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class LoginRequest(BaseModel):
    email: str
    password: str


class OrderRequest(BaseModel):
    offer_id: str
    requested_duration_minutes: int = 60


class RedeemRequest(BaseModel):
    access_code: str


class RuntimeSessionRequest(BaseModel):
    access_code: str
    network_mode: str = "wireguard"


class WorkspaceSelectRequest(BaseModel):
    path: str


class AssistantMessageRequest(BaseModel):
    message: str = Field(min_length=1)


@app.exception_handler(LocalAppError)
def handle_local_error(_: Request, exc: LocalAppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Exception)
def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "step": "buyer_client",
                "code": "buyer_internal_error",
                "message": "Buyer client encountered an unexpected internal error.",
                "hint": "Inspect the local buyer-client logs and retry after fixing the reported issue.",
                "details": {"exception": str(exc)},
            }
        },
    )


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.post("/local-api/auth/login")
def local_login(payload: LoginRequest) -> dict[str, Any]:
    client = BackendClient(settings)
    try:
        response = client.login(payload.email, payload.password)
    except BackendClientError as exc:
        raise _backend_error("auth.login", exc, "Failed to log in to the platform backend.", "Confirm the backend URL, buyer account, password, and outbound HTTPS connectivity.") from exc
    state.set_auth(response["access_token"], response["user"])
    return {"user": response["user"], "expires_at": response["expires_at"]}


@app.get("/local-api/catalog/offers")
def local_catalog() -> list[dict[str, Any]]:
    client = _require_backend_client()
    try:
        offers = client.catalog_offers()
    except BackendClientError as exc:
        raise _backend_error("catalog.fetch", exc, "Failed to fetch buyer catalog offers.", "Check public HTTPS connectivity to the platform backend.") from exc
    state.set_catalog(offers)
    return offers


@app.post("/local-api/orders")
def local_order(payload: OrderRequest) -> dict[str, Any]:
    client = _require_backend_client()
    try:
        response = client.create_order(payload.offer_id, payload.requested_duration_minutes)
    except BackendClientError as exc:
        raise _backend_error("order.create", exc, "Failed to create the buyer order.", "Confirm the selected offer is still available and retry.") from exc
    state.set_order(response)
    return response


@app.post("/local-api/access-codes/redeem")
def local_redeem(payload: RedeemRequest) -> dict[str, Any]:
    client = _require_backend_client()
    try:
        response = client.redeem_access_code(payload.access_code)
    except BackendClientError as exc:
        raise _backend_error("access_code.redeem", exc, "Failed to redeem the buyer access code.", "Confirm the access code is valid, unexpired, and owned by the current buyer.") from exc
    state.set_redeemed_access_code(response)
    return response


@app.post("/local-api/runtime-sessions")
def local_runtime_session(payload: RuntimeSessionRequest) -> dict[str, Any]:
    client = _require_backend_client()
    private_key, public_key = generate_keypair()
    try:
        runtime_session = client.create_runtime_session(payload.access_code, public_key, payload.network_mode)
        connect_material = client.get_connect_material(runtime_session["id"])
        bootstrap = client.get_bootstrap_config(runtime_session["id"])
    except BackendClientError as exc:
        raise _backend_error("runtime_session.create", exc, "Failed to create the buyer runtime session.", "Confirm the access code was redeemed and the target runtime image satisfies the current runtime contract.") from exc
    bootstrap["wireguard_private_key"] = private_key
    bootstrap["connect_material"] = connect_material
    state.set_runtime_session(runtime_session, bootstrap)
    state.start_heartbeat(client, runtime_session["id"])
    prepare_codex_session(settings=settings, state=state, runtime_session_id=runtime_session["id"], bootstrap_config=bootstrap)
    return {
        "runtime_session": runtime_session,
        "connect_material": connect_material,
        "bootstrap_config": bootstrap,
    }


@app.get("/local-api/runtime-sessions/current")
def local_runtime_session_current() -> dict[str, Any]:
    return state.runtime_snapshot()


@app.post("/local-api/env/scan")
def local_env_scan() -> dict[str, Any]:
    client = BackendClient(settings, token=state.auth_token()) if state.auth_token() else None
    report = scan_environment(settings, client)
    state.set_env_report(report)
    runtime_session = state.current_runtime_session()
    if runtime_session and client is not None:
        try:
            client_session = client.post_env_report(runtime_session["id"], report)
        except BackendClientError as exc:
            raise _backend_error("env_scan.sync", exc, "The buyer environment scan completed, but the report could not be uploaded to the platform.", "Check backend connectivity and whether the runtime session is still active.") from exc
        return {"report": report, "client_session": client_session}
    return report


@app.post("/local-api/wireguard/up")
def local_wireguard_up() -> dict[str, Any]:
    bootstrap = _require_bootstrap()
    runtime_session = _require_runtime_session()
    profile = bootstrap.get("wireguard_profile") or {}
    private_key = bootstrap.get("wireguard_private_key")
    paths = state.session_paths(runtime_session["id"])
    config_path = paths.wireguard_dir / f"{settings.wireguard_tunnel_prefix}-{runtime_session['id'][:8]}.conf"
    write_config(config_path=config_path, private_key=private_key, profile=profile)
    tunnel_name = install_tunnel(config_path)
    payload = {"status": "up", "config_path": str(config_path), "tunnel_name": tunnel_name}
    state.set_wireguard_state(payload)
    return payload


@app.post("/local-api/wireguard/down")
def local_wireguard_down() -> dict[str, Any]:
    runtime_session = _require_runtime_session()
    tunnel_name = f"{settings.wireguard_tunnel_prefix}-{runtime_session['id'][:8]}"
    remove_tunnel(tunnel_name)
    state.set_wireguard_state({"status": "down", "tunnel_name": tunnel_name})
    return {"status": "down", "tunnel_name": tunnel_name}


@app.get("/local-api/shell/session")
def local_shell_session() -> dict[str, Any]:
    bootstrap = _require_bootstrap()
    return {
        "shell_embed_url": bootstrap.get("shell_embed_url"),
        "public_gateway_access_url": bootstrap.get("public_gateway_access_url"),
        "wireguard_gateway_access_url": bootstrap.get("wireguard_gateway_access_url"),
    }


@app.post("/local-api/workspace/select")
def local_workspace_select(payload: WorkspaceSelectRequest) -> dict[str, Any]:
    workspace_path = str(Path(payload.path).expanduser())
    state.set_workspace_path(workspace_path)
    return {"workspace_path": workspace_path}


@app.post("/local-api/workspace/sync")
def local_workspace_sync() -> dict[str, Any]:
    workspace_path = state.current_workspace_path()
    bootstrap = _require_bootstrap()
    if not workspace_path:
        raise LocalAppError(
            step="workspace.select",
            code="workspace_path_missing",
            message="A local workspace path has not been selected.",
            hint="Select a local folder before syncing code into the buyer runtime.",
            status_code=409,
        )
    archive_path = package_workspace(Path(workspace_path), settings.workspace_archive_name)
    result = sync_workspace(
        archive_path,
        bootstrap.get("workspace_sync_url"),
        bootstrap.get("workspace_extract_url"),
    )
    return {"workspace_path": workspace_path, "archive_path": str(archive_path), "sync_result": result}


@app.post("/local-api/assistant/message")
def local_assistant(payload: AssistantMessageRequest) -> dict[str, Any]:
    runtime_session = _require_runtime_session()
    job = state.jobs.submit(
        "assistant_message",
        lambda: run_codex_assistant(
            settings=settings,
            state=state,
            runtime_session_id=runtime_session["id"],
            user_message=payload.message,
        ),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/runtime-sessions/stop")
def local_runtime_stop() -> dict[str, Any]:
    client = _require_backend_client()
    runtime_session = _require_runtime_session()
    try:
        response = client.stop_runtime_session(runtime_session["id"])
    except BackendClientError as exc:
        raise _backend_error("runtime_session.stop", exc, "Failed to stop the buyer runtime session.", "Retry after confirming the runtime session is still active.") from exc
    return response


@app.post("/local-api/runtime-sessions/close")
def local_runtime_close() -> dict[str, Any]:
    client = _require_backend_client()
    runtime_session = _require_runtime_session()
    try:
        response = client.close_runtime_session(runtime_session["id"])
    except BackendClientError as exc:
        raise _backend_error("runtime_session.close", exc, "Failed to close the buyer runtime client session.", "Retry after confirming the backend is reachable.") from exc
    cleanup_codex_session(settings=settings, state=state, runtime_session_id=runtime_session["id"])
    return response


@app.get("/local-api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = state.jobs.get(job_id)
    if job is None:
        raise LocalAppError(step="job", code="job_not_found", message="Job not found.", hint="Refresh the buyer-client state and retry.", status_code=404)
    return {
        "job_id": job.job_id,
        "name": job.name,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "result": job.result,
        "error": job.error,
    }


def _require_backend_client() -> BackendClient:
    token = state.auth_token()
    if not token:
        raise LocalAppError(step="auth", code="not_logged_in", message="The buyer client is not logged in.", hint="Log in to the platform before running buyer actions.", status_code=401)
    return BackendClient(settings, token=token)


def _require_runtime_session() -> dict[str, Any]:
    runtime_session = state.current_runtime_session()
    if runtime_session is None:
        raise LocalAppError(step="runtime_session", code="runtime_session_missing", message="Buyer runtime session is not initialized.", hint="Create a runtime session before trying to connect or sync code.", status_code=409)
    return runtime_session


def _require_bootstrap() -> dict[str, Any]:
    bootstrap = state.current_bootstrap_config()
    if bootstrap is None:
        raise LocalAppError(step="runtime_session", code="runtime_bootstrap_missing", message="Buyer runtime bootstrap config is not initialized.", hint="Refresh buyer connect material and bootstrap config before continuing.", status_code=409)
    return bootstrap


def _backend_error(step: str, exc: BackendClientError, message: str, hint: str) -> LocalAppError:
    return LocalAppError(
        step=step,
        code="backend_request_failed",
        message=message,
        hint=hint,
        details={"backend": exc.payload or {"detail": exc.detail}},
        status_code=exc.status_code if exc.status_code >= 400 else 502,
    )
