from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from seller_client_app.backend import BackendClient, BackendClientError
from seller_client_app.codex_session import CodexSessionError, cleanup_codex_session, prepare_codex_session, run_codex_assistant
from seller_client_app.config import get_settings
from seller_client_app.env_scan import scan_environment
from seller_client_app.errors import LocalAppError
from seller_client_app.state import SellerClientState
from seller_client_app.ubuntu_compute import (
    bootstrap_ubuntu_compute,
    collect_wireguard_node_status,
    detect_ubuntu_swarm_info,
    detect_ubuntu_swarm_node_ref,
    join_swarm_from_ubuntu,
    scan_ubuntu_compute,
    sync_context_to_ubuntu,
)
from seller_client_app.ubuntu_image_builder import (
    UbuntuImageBuilderError,
    build_image_in_ubuntu,
    generate_dockerfile_template,
    push_image_from_ubuntu,
)
from seller_client_app.ubuntu_standard_image import pull_standard_image, verify_standard_image
from seller_client_app.windows_host import run_windows_host_install_and_check

settings = get_settings()
state = SellerClientState(settings)
app = FastAPI(title="Pivot Seller Client", version="0.2.0")
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class LoginRequest(BaseModel):
    email: str
    password: str


class OnboardingStartRequest(BaseModel):
    requested_accelerator: str = "gpu"
    requested_compute_node_id: str | None = None


class AssistantMessageRequest(BaseModel):
    message: str = Field(min_length=1)


class UbuntuContextSyncRequest(BaseModel):
    local_path: str
    ubuntu_target_path: str | None = None


class NodeClaimRequest(BaseModel):
    node_ref: str | None = None
    compute_node_id: str | None = None
    requested_accelerator: str | None = None


class ImageBuildRequest(BaseModel):
    repository: str
    tag: str
    registry: str
    dockerfile_content: str | None = None
    extra_dockerfile_lines: list[str] = Field(default_factory=list)
    resource_profile: dict[str, Any] = Field(default_factory=dict)


class ImagePushRequest(BaseModel):
    image_ref: str | None = None


class ImageReportRequest(BaseModel):
    node_ref: str
    runtime_image_ref: str
    repository: str
    tag: str
    registry: str


class WindowsHostScriptRequest(BaseModel):
    mode: Literal["check", "install", "all"] = "all"


@app.exception_handler(LocalAppError)
def handle_local_app_error(_: Request, exc: LocalAppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Exception)
def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, LocalAppError):
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "step": "local_api",
                "code": "local_internal_error",
                "message": "Seller client encountered an unexpected internal error.",
                "hint": "Check the local seller-client service logs and retry after fixing the reported issue.",
                "details": {"exception": str(exc)},
            }
        },
    )


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.post("/local-api/window-session/open")
def window_session_open() -> dict[str, Any]:
    previous_window = state.current_window_session()
    previous_onboarding = state.current_onboarding_session()
    if previous_window and previous_onboarding:
        if state.auth_token():
            client = BackendClient(settings, token=state.auth_token())
            try:
                client.close_onboarding_session(previous_onboarding["session_id"])
            except BackendClientError:
                pass
        cleanup_codex_session(
            settings=settings,
            state=state,
            session_id=previous_onboarding["session_id"],
        )
        state.close_window_session(previous_window["session_id"])
    return state.open_window_session()


@app.post("/local-api/window-session/heartbeat")
def window_session_heartbeat(request: Request) -> dict[str, Any]:
    window_session = _require_window_session(request)
    return state.heartbeat_window_session(window_session["session_id"])


@app.post("/local-api/window-session/close")
def window_session_close(session_id: str | None = Query(default=None)) -> dict[str, Any]:
    current = state.current_window_session()
    if current is None:
        return {"status": "already_closed"}

    session_payload = state.current_onboarding_session()
    closed = state.close_window_session(session_id or current["session_id"])
    if closed is None:
        raise LocalAppError(
            step="window_session.close",
            code="window_session_mismatch",
            message="Cannot close a different browser window session.",
            hint="Close the currently active seller console window session instead.",
            status_code=409,
        )

    if session_payload is not None:
        if state.auth_token():
            client = BackendClient(settings, token=state.auth_token())
            try:
                client.close_onboarding_session(session_payload["session_id"])
            except BackendClientError:
                pass
        cleanup_codex_session(
            settings=settings,
            state=state,
            session_id=session_payload["session_id"],
        )
    return {"status": "closed", "window_session": closed}


@app.post("/local-api/auth/login")
def local_login(payload: LoginRequest) -> dict[str, Any]:
    client = BackendClient(settings)
    try:
        response = client.login(payload.email, payload.password)
    except BackendClientError as exc:
        raise _backend_error(
            "auth.login",
            exc,
            message="Failed to log in to the platform backend.",
            hint="Confirm the backend URL, seller account, password, and outbound HTTPS connectivity.",
        ) from exc
    state.set_auth(response["access_token"], response["user"])
    return {
        "user": response["user"],
        "expires_at": response["expires_at"],
    }


@app.post("/local-api/onboarding/start")
def onboarding_start(payload: OnboardingStartRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        session_payload = client.create_onboarding_session(
            requested_accelerator=payload.requested_accelerator,
            requested_compute_node_id=payload.requested_compute_node_id,
        )
        bootstrap_config = client.get_bootstrap_config(session_payload["session_id"])
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.start",
            exc,
            message="Failed to create the seller onboarding session.",
            hint="Confirm backend connectivity and seller permissions, then retry.",
        ) from exc

    paths = state.set_onboarding(session_payload, bootstrap_config)
    try:
        prepare_codex_session(
            settings=settings,
            state=state,
            session_id=session_payload["session_id"],
            bootstrap_config=bootstrap_config,
        )
    except CodexSessionError as exc:
        raise LocalAppError(
            step="onboarding.codex",
            code="codex_session_init_failed",
            message="Failed to initialize the window-scoped Codex environment.",
            hint="Check that Codex CLI is installed and callable on this machine before retrying onboarding.",
            details={"exception": str(exc), "session_id": session_payload["session_id"]},
            status_code=500,
        ) from exc

    state.start_heartbeat(client, session_payload["session_id"])
    return {
        "session": session_payload,
        "bootstrap_config": bootstrap_config,
        "window_session": state.current_window_session(),
        "paths": {
            "session_root": str(paths.session_root),
            "workspace_dir": str(paths.workspace_dir),
            "logs_dir": str(paths.logs_dir),
        },
    }


@app.get("/local-api/onboarding/current")
def onboarding_current(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    return state.runtime_snapshot()


@app.post("/local-api/windows-host/install-and-check")
def local_windows_host_install_and_check(payload: WindowsHostScriptRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)

    def _task() -> dict[str, Any]:
        output_path = _windows_host_report_path()
        report = run_windows_host_install_and_check(settings, mode=payload.mode, output_path=output_path)
        state.set_last_env_report(report)
        session_payload = state.current_onboarding_session()
        if session_payload and state.auth_token():
            client = BackendClient(settings, token=state.auth_token())
            updated = client.post_host_env_report(session_payload["session_id"], report)
            state.update_onboarding_session(updated)
        return report

    job = state.jobs.submit("windows_host_install_and_check", _task)
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/env/scan")
def local_env_scan(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = BackendClient(settings, token=state.auth_token())
    report = scan_environment(settings, client)
    state.set_last_env_report(report)
    session_payload = state.current_onboarding_session()
    if session_payload:
        try:
            updated = client.post_host_env_report(session_payload["session_id"], report)
        except BackendClientError as exc:
            raise LocalAppError(
                step="env_scan.sync",
                code="env_report_upload_failed",
                message="The local environment scan completed, but the report could not be uploaded to the platform.",
                hint="Check backend connectivity and whether the onboarding session is still active, then retry sync.",
                details={"scan_report": report, "backend_error": exc.payload or {"detail": exc.detail}},
                status_code=502,
            ) from exc
        state.update_onboarding_session(updated)
    return report


@app.get("/local-api/ubuntu/bootstrap")
def local_ubuntu_bootstrap(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        return client.get_ubuntu_bootstrap(session_payload["session_id"])
    except BackendClientError as exc:
        raise _backend_error(
            "ubuntu.bootstrap",
            exc,
            message="Failed to fetch Ubuntu compute bootstrap configuration.",
            hint="Confirm the onboarding session is active and backend compute bootstrap policy is configured.",
        ) from exc


@app.post("/local-api/ubuntu/host-env/scan")
def local_windows_host_scan(request: Request) -> dict[str, Any]:
    return local_env_scan(request)


@app.post("/local-api/ubuntu/env/scan")
def local_ubuntu_scan(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    report = scan_ubuntu_compute(settings)
    try:
        updated = client.post_ubuntu_env_report(session_payload["session_id"], report)
    except BackendClientError as exc:
        raise _backend_error(
            "ubuntu.env_scan",
            exc,
            message="Ubuntu compute scan completed, but the report could not be uploaded to the platform.",
            hint="Confirm backend connectivity and onboarding session validity before retrying.",
        ) from exc
    state.set_last_env_report(report)
    state.update_onboarding_session(updated)
    return report


@app.post("/local-api/ubuntu/bootstrap-run")
def local_ubuntu_bootstrap_run(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        ubuntu_bootstrap = client.get_ubuntu_bootstrap(session_payload["session_id"])
    except BackendClientError as exc:
        raise _backend_error(
            "ubuntu.bootstrap_run",
            exc,
            message="Failed to fetch Ubuntu bootstrap before execution.",
            hint="Refresh the onboarding session and retry.",
        ) from exc
    return bootstrap_ubuntu_compute(settings, ubuntu_bootstrap)


@app.post("/local-api/ubuntu/context-sync")
def local_ubuntu_context_sync(payload: UbuntuContextSyncRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    result = sync_context_to_ubuntu(settings, payload.local_path, payload.ubuntu_target_path)
    state.set_last_context_sync(result)
    return result


@app.post("/local-api/ubuntu/standard-image/pull")
def local_standard_image_pull(request: Request) -> dict[str, Any]:
    _require_window_session(request)

    def _task() -> dict[str, Any]:
        client = _require_backend_client()
        session_payload = _require_onboarding_session()
        ubuntu_bootstrap = client.get_ubuntu_bootstrap(session_payload["session_id"])
        result = pull_standard_image(settings, ubuntu_bootstrap)
        state.set_last_standard_image_pull(result)
        return result

    job = state.jobs.submit("pull_standard_image", _task)
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/ubuntu/standard-image/verify")
def local_standard_image_verify(request: Request) -> dict[str, Any]:
    _require_window_session(request)

    def _task() -> dict[str, Any]:
        client = _require_backend_client()
        session_payload = _require_onboarding_session()
        ubuntu_bootstrap = client.get_ubuntu_bootstrap(session_payload["session_id"])
        result = verify_standard_image(
            settings,
            ubuntu_bootstrap,
            session_id=session_payload["session_id"],
            requested_accelerator=session_payload.get("requested_accelerator") or "gpu",
        )
        state.set_last_standard_image_verify(result)
        return result

    job = state.jobs.submit("verify_standard_image", _task)
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/ubuntu/swarm-join")
def local_ubuntu_swarm_join(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    ubuntu_bootstrap = client.get_ubuntu_bootstrap(session_payload["session_id"])
    state.set_last_join_material(ubuntu_bootstrap["ubuntu_compute_bootstrap"]["swarm_join"])
    result = join_swarm_from_ubuntu(settings, ubuntu_bootstrap)
    return {
        **result,
        "swarm_info": detect_ubuntu_swarm_info(settings),
        "node_ref": detect_ubuntu_swarm_node_ref(settings),
    }


@app.get("/local-api/node/wireguard-status")
def local_node_wireguard_status(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    ubuntu_bootstrap = client.get_ubuntu_bootstrap(session_payload["session_id"])
    node_status = collect_wireguard_node_status(
        settings,
        expected_node_addr=ubuntu_bootstrap["ubuntu_compute_bootstrap"]["expected_node_addr"],
        backend_client=client,
    )
    state.set_last_wireguard_status(node_status)
    return node_status


@app.post("/local-api/ubuntu/compute-ready")
def local_ubuntu_compute_ready(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    node_ref = detect_ubuntu_swarm_node_ref(settings)
    ubuntu_bootstrap = client.get_ubuntu_bootstrap(session_payload["session_id"])
    node_status = collect_wireguard_node_status(
        settings,
        expected_node_addr=ubuntu_bootstrap["ubuntu_compute_bootstrap"]["expected_node_addr"],
        backend_client=client,
        node_ref=node_ref,
    )
    state.set_last_wireguard_status(node_status)
    if not node_status["wireguard_addr_match"]:
        raise LocalAppError(
            step="ubuntu.compute_ready",
            code="wireguard_node_addr_mismatch",
            message="Ubuntu swarm node is not using the expected WireGuard address yet.",
            hint="Re-run standard image verification and swarm join until NodeAddr matches the backend-provided WireGuard address.",
            details={"node_status": node_status},
            status_code=409,
        )
    try:
        updated = client.post_compute_ready(
            session_payload["session_id"],
            {
                "node_ref": node_ref,
                "swarm_info": detect_ubuntu_swarm_info(settings),
                "node_status": node_status,
            },
        )
    except BackendClientError as exc:
        raise _backend_error(
            "ubuntu.compute_ready",
            exc,
            message="Failed to mark the Ubuntu compute environment as ready.",
            hint="Ensure Ubuntu Docker successfully joined the Swarm cluster before retrying.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/assistant/message")
def assistant_message(payload: AssistantMessageRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    session_payload = state.current_onboarding_session()
    if not session_payload:
        raise LocalAppError(
            step="assistant.message",
            code="onboarding_session_missing",
            message="Onboarding session is not initialized.",
            hint="Start a seller onboarding session before using the natural language assistant.",
            status_code=409,
        )

    job = state.jobs.submit(
        "assistant_message",
        lambda: run_codex_assistant(
            settings=settings,
            state=state,
            session_id=session_payload["session_id"],
            user_message=payload.message,
        ),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/node/claim")
def local_claim_node(payload: NodeClaimRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    node_ref = payload.node_ref or detect_ubuntu_swarm_node_ref(settings)
    compute_node_id = payload.compute_node_id or session_payload.get("requested_compute_node_id")
    requested_accelerator = payload.requested_accelerator or session_payload.get("requested_accelerator") or "gpu"
    if not compute_node_id:
        raise LocalAppError(
            step="node.claim",
            code="compute_node_id_required",
            message="compute_node_id is required before claiming a seller node.",
            hint="Provide a compute node id in the UI or start onboarding with a predefined compute node id.",
            status_code=422,
        )

    try:
        response = client.claim_node(
            node_ref=node_ref,
            onboarding_session_id=session_payload["session_id"],
            compute_node_id=compute_node_id,
            requested_accelerator=requested_accelerator,
        )
    except BackendClientError as exc:
        raise _backend_error(
            "node.claim",
            exc,
            message="Failed to claim the seller node in the platform.",
            hint=(
                "Check whether the manager can see this node, whether the node already joined the correct swarm, "
                "and whether the onboarding session still matches the requested compute node id."
            ),
            details={"node_ref": node_ref, "compute_node_id": compute_node_id},
        ) from exc

    updated = client.get_onboarding_session(session_payload["session_id"])
    state.update_onboarding_session(updated)
    return {"claim": response, "session": updated}


@app.post("/local-api/ubuntu/image/build")
def local_ubuntu_image_build(payload: ImageBuildRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    session_payload = _require_onboarding_session()
    policy = _require_policy()
    runtime_paths = state.session_paths(session_payload["session_id"])
    context_sync = _require_context_sync()

    def _task() -> dict[str, Any]:
        dockerfile_content = payload.dockerfile_content or generate_dockerfile_template(
            policy,
            payload.extra_dockerfile_lines,
        )
        artifact = build_image_in_ubuntu(
            settings=settings,
            session_runtime_dir=runtime_paths.session_root,
            policy=policy,
            repository=payload.repository,
            tag=payload.tag,
            registry=payload.registry,
            dockerfile_content=dockerfile_content,
            ubuntu_context_path=context_sync["ubuntu_target"],
            resource_profile=payload.resource_profile,
        )
        build_payload = {
            "image_ref": artifact.image_ref,
            "repository": artifact.repository,
            "tag": artifact.tag,
            "registry": artifact.registry,
            "ubuntu_context_path": artifact.ubuntu_context_path,
            "ubuntu_dockerfile_path": artifact.ubuntu_dockerfile_path,
            "dockerfile_path": str(artifact.local_dockerfile_path),
            "metadata_path": str(artifact.local_metadata_path),
            "resource_profile": payload.resource_profile,
        }
        state.set_last_build(build_payload)
        return build_payload

    job = state.jobs.submit("build_image_in_ubuntu", _task)
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/ubuntu/image/push")
def local_ubuntu_image_push(payload: ImagePushRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    last_build = state.last_build()
    image_ref = payload.image_ref or (last_build or {}).get("image_ref")
    if not image_ref:
        raise LocalAppError(
            step="image.push",
            code="image_ref_required",
            message="image_ref is required before pushing an image from Ubuntu.",
            hint="Run an Ubuntu image build first or explicitly provide the image ref to push.",
            status_code=422,
        )

    job = state.jobs.submit("push_image_from_ubuntu", lambda: _push_image_job(image_ref))
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/image/report")
def local_image_report(payload: ImageReportRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    job = state.jobs.submit(
        "report_image",
        lambda: client.report_image(
            node_ref=payload.node_ref,
            runtime_image_ref=payload.runtime_image_ref,
            repository=payload.repository,
            tag=payload.tag,
            registry=payload.registry,
        ),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.get("/local-api/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    job = state.jobs.get(job_id)
    if job is None:
        raise LocalAppError(
            step="job",
            code="job_not_found",
            message="Job not found.",
            hint="Refresh the local seller console state and retry.",
            status_code=404,
        )
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


@app.post("/local-api/onboarding/close")
def onboarding_close(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        session_response = client.close_onboarding_session(session_payload["session_id"])
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.close",
            exc,
            message="Failed to close the seller onboarding session.",
            hint="Retry closing the onboarding session after the backend becomes reachable.",
        ) from exc

    cleanup_codex_session(
        settings=settings,
        state=state,
        session_id=session_payload["session_id"],
    )
    return {"session": session_response, "status": "closed"}


def _require_backend_client() -> BackendClient:
    token = state.auth_token()
    if not token:
        raise LocalAppError(
            step="auth",
            code="not_logged_in",
            message="The seller client is not logged in.",
            hint="Log in to the platform before starting onboarding actions.",
            status_code=401,
        )
    return BackendClient(settings, token=token)


def _require_window_session(request: Request) -> dict[str, Any]:
    session_id = request.headers.get("X-Window-Session-Id")
    return state.require_window_session(session_id)


def _require_onboarding_session() -> dict[str, Any]:
    session_payload = state.current_onboarding_session()
    if session_payload is None:
        raise LocalAppError(
            step="onboarding",
            code="onboarding_session_missing",
            message="Onboarding session is not initialized.",
            hint="Start a seller onboarding session before running this action.",
            status_code=409,
        )
    return session_payload


def _require_policy() -> dict[str, Any]:
    bootstrap = state.current_bootstrap_config()
    if bootstrap is None:
        raise LocalAppError(
            step="policy",
            code="bootstrap_config_missing",
            message="Bootstrap config is not initialized.",
            hint="Restart onboarding so the seller client can fetch the latest platform policy.",
            status_code=409,
        )
    return bootstrap["policy"]


def _require_context_sync() -> dict[str, Any]:
    context_sync = state.last_context_sync()
    if context_sync is None:
        raise LocalAppError(
            step="ubuntu.image.build",
            code="context_sync_required",
            message="Ubuntu build context is not prepared yet.",
            hint="Sync a Windows directory into Ubuntu before building the runtime image.",
            status_code=409,
        )
    return context_sync


def _windows_host_report_path() -> Path:
    session_payload = state.current_onboarding_session()
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    if session_payload is None:
        output_dir = settings.workspace_root_path / "windows-host"
    else:
        output_dir = state.session_paths(session_payload["session_id"]).logs_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"windows-host-check-{timestamp}.json"


def _push_image_job(image_ref: str) -> dict[str, Any]:
    try:
        push_image_from_ubuntu(settings, image_ref)
    except UbuntuImageBuilderError as exc:
        raise LocalAppError(
            step="image.push",
            code="ubuntu_docker_push_failed",
            message="Ubuntu docker push failed for the selected runtime image.",
            hint="Check Ubuntu Docker login state, registry connectivity, and whether the image ref points to the allowed registry.",
            details={"image_ref": image_ref, "exception": str(exc)},
            status_code=502,
        ) from exc
    return {"status": "pushed", "image_ref": image_ref, "executor": "wsl_ubuntu"}


def _backend_error(
    step: str,
    exc: BackendClientError,
    *,
    message: str,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> LocalAppError:
    backend_payload = exc.payload or {"detail": exc.detail}
    merged_details = {"backend": backend_payload}
    if details:
        merged_details.update(details)
    return LocalAppError(
        step=step,
        code="backend_request_failed",
        message=message,
        hint=hint,
        details=merged_details,
        status_code=exc.status_code if exc.status_code >= 400 else 502,
    )
