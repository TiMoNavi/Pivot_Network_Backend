from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from seller_client_app.backend import BackendClient, BackendClientError
from seller_client_app.codex_session import CodexSessionError, cleanup_codex_session, prepare_codex_session, run_codex_assistant
from seller_client_app.config import get_settings
from seller_client_app.docker_workbench import DockerWorkbenchError, build_image, generate_dockerfile_template, push_image
from seller_client_app.env_scan import scan_environment
from seller_client_app.errors import LocalAppError
from seller_client_app.state import SellerClientState
from seller_client_app.ubuntu_compute import (
    bootstrap_ubuntu_compute,
    detect_ubuntu_swarm_info,
    detect_ubuntu_swarm_node_ref,
    join_swarm_from_ubuntu,
    scan_ubuntu_compute,
    sync_context_to_ubuntu,
)

settings = get_settings()
state = SellerClientState(settings)
app = FastAPI(title="Pivot Seller Client", version="0.1.0")
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


class JoinRunRequest(BaseModel):
    force_refresh_join_material: bool = False


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
def onboarding_start(payload: OnboardingStartRequest) -> dict[str, Any]:
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
            message="Failed to initialize the session-scoped Codex environment.",
            hint="Check that Codex CLI is installed and callable on this machine before retrying onboarding.",
            details={"exception": str(exc), "session_id": session_payload["session_id"]},
            status_code=500,
        ) from exc
    state.start_heartbeat(client, session_payload["session_id"])
    return {
        "session": session_payload,
        "bootstrap_config": bootstrap_config,
        "paths": {
            "session_root": str(paths.session_root),
            "workspace_dir": str(paths.workspace_dir),
            "logs_dir": str(paths.logs_dir),
        },
    }


@app.get("/local-api/onboarding/current")
def onboarding_current() -> dict[str, Any]:
    return state.runtime_snapshot()


@app.post("/local-api/env/scan")
def local_env_scan() -> dict[str, Any]:
    client = BackendClient(settings, token=state.auth_token()) if state.auth_token() else None
    report = scan_environment(settings, client)
    state.set_last_env_report(report)
    session_payload = state.current_onboarding_session()
    if session_payload and client is not None:
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
def local_ubuntu_bootstrap() -> dict[str, Any]:
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
def local_windows_host_scan() -> dict[str, Any]:
    return local_env_scan()


@app.post("/local-api/ubuntu/env/scan")
def local_ubuntu_scan() -> dict[str, Any]:
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
    state.update_onboarding_session(updated)
    return report


@app.post("/local-api/ubuntu/bootstrap-run")
def local_ubuntu_bootstrap_run() -> dict[str, Any]:
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
def local_ubuntu_context_sync(payload: UbuntuContextSyncRequest) -> dict[str, Any]:
    return sync_context_to_ubuntu(settings, payload.local_path, payload.ubuntu_target_path)


@app.post("/local-api/ubuntu/swarm-join")
def local_ubuntu_swarm_join(payload: JoinRunRequest) -> dict[str, Any]:
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    ubuntu_bootstrap = client.get_ubuntu_bootstrap(session_payload["session_id"])
    result = join_swarm_from_ubuntu(settings, ubuntu_bootstrap)
    return {
        **result,
        "swarm_info": detect_ubuntu_swarm_info(settings),
        "node_ref": detect_ubuntu_swarm_node_ref(settings),
    }


@app.post("/local-api/ubuntu/compute-ready")
def local_ubuntu_compute_ready() -> dict[str, Any]:
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    node_ref = detect_ubuntu_swarm_node_ref(settings)
    try:
        updated = client.post_compute_ready(
            session_payload["session_id"],
            {
                "node_ref": node_ref,
                "swarm_info": detect_ubuntu_swarm_info(settings),
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
def assistant_message(payload: AssistantMessageRequest) -> dict[str, Any]:
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


@app.post("/local-api/join/run")
def join_run(payload: JoinRunRequest) -> dict[str, Any]:
    return local_ubuntu_swarm_join(payload)


@app.post("/local-api/node/claim")
def local_claim_node(payload: NodeClaimRequest) -> dict[str, Any]:
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


@app.post("/local-api/image/build")
def local_image_build(payload: ImageBuildRequest) -> dict[str, Any]:
    session_payload = _require_onboarding_session()
    policy = _require_policy()
    runtime_paths = state.session_paths(session_payload["session_id"])

    def _task() -> dict[str, Any]:
        dockerfile_content = payload.dockerfile_content or generate_dockerfile_template(
            policy,
            payload.extra_dockerfile_lines,
        )
        artifact = build_image(
            settings=settings,
            session_runtime_dir=runtime_paths.session_root,
            policy=policy,
            repository=payload.repository,
            tag=payload.tag,
            registry=payload.registry,
            dockerfile_content=dockerfile_content,
            resource_profile=payload.resource_profile,
        )
        build_payload = {
            "image_ref": artifact.image_ref,
            "repository": artifact.repository,
            "tag": artifact.tag,
            "registry": artifact.registry,
            "dockerfile_path": str(artifact.dockerfile_path),
            "metadata_path": str(artifact.metadata_path),
            "resource_profile": payload.resource_profile,
        }
        state.set_last_build(build_payload)
        return build_payload

    job = state.jobs.submit("build_image", _task)
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/image/push")
def local_image_push(payload: ImagePushRequest) -> dict[str, Any]:
    last_build = state.last_build()
    image_ref = payload.image_ref or (last_build or {}).get("image_ref")
    if not image_ref:
        raise LocalAppError(
            step="image.push",
            code="image_ref_required",
            message="image_ref is required before pushing an image.",
            hint="Run a local image build first or explicitly provide the image ref to push.",
            status_code=422,
        )

    job = state.jobs.submit("push_image", lambda: _push_image_job(image_ref))
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/image/report")
def local_image_report(payload: ImageReportRequest) -> dict[str, Any]:
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
def get_job(job_id: str) -> dict[str, Any]:
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
def onboarding_close() -> dict[str, Any]:
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


def _detect_local_node_ref() -> str:
    return detect_ubuntu_swarm_node_ref(settings)


def _push_image_job(image_ref: str) -> dict[str, Any]:
    try:
        push_image(image_ref)
    except DockerWorkbenchError as exc:
        raise LocalAppError(
            step="image.push",
            code="docker_push_failed",
            message="Docker push failed for the selected runtime image.",
            hint="Check registry connectivity, Docker login state, and whether the image ref points to the allowed registry.",
            details={"image_ref": image_ref, "exception": str(exc)},
            status_code=502,
        ) from exc
    return {"status": "pushed", "image_ref": image_ref}


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
