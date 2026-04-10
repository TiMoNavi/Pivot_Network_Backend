from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from seller_client_app.assistant_runtime import execute_assistant_request
from seller_client_app.backend import BackendClient, BackendClientError
from seller_client_app.codex_session import CodexSessionError, cleanup_codex_session, prepare_codex_session
from seller_client_app.config import get_settings
from seller_client_app.errors import LocalAppError
from seller_client_app.local_system import (
    clear_join_state as perform_clear_join_state,
    collect_environment_health,
    export_diagnostics_bundle,
    prepare_machine_wireguard_config,
    run_overlay_runtime_check,
    run_standard_join_workflow,
    verify_manager_task_execution,
)
from seller_client_app.mcp_http import (
    McpHttpResponse,
    build_mcp_http_delete_response,
    build_mcp_http_get_response,
    build_mcp_http_post_response,
)
from seller_client_app.onboarding import build_phase1_drafts_from_session
from seller_client_app.state import SellerClientState

settings = get_settings()
state = SellerClientState(settings)
app = FastAPI(title="Pivot Seller Client", version="0.2.0")
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class RegisterRequest(StrictModel):
    email: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=8)
    role: str = "seller"


class OnboardingStartRequest(StrictModel):
    requested_accelerator: str = "gpu"
    requested_compute_node_id: str | None = None
    requested_offer_tier: str | None = None
    expected_wireguard_ip: str | None = None


class OnboardingAttachRequest(StrictModel):
    session_id: str = Field(min_length=1)


class AssistantMessageRequest(StrictModel):
    message: str = Field(min_length=1)


class LinuxHostProbeRequest(StrictModel):
    reported_phase: str | None = None
    host_name: str | None = None
    os_name: str | None = None
    distribution_name: str | None = None
    kernel_release: str | None = None
    virtualization_available: bool | None = None
    sudo_available: bool | None = None
    observed_ips: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class LinuxSubstrateProbeRequest(StrictModel):
    reported_phase: str | None = None
    distribution_name: str | None = None
    kernel_release: str | None = None
    docker_available: bool | None = None
    docker_version: str | None = None
    wireguard_available: bool | None = None
    gpu_available: bool | None = None
    cpu_cores: int | None = None
    memory_gb: int | None = None
    disk_free_gb: int | None = None
    observed_ips: list[str] = Field(default_factory=list)
    observed_wireguard_ip: str | None = None
    observed_advertise_addr: str | None = None
    observed_data_path_addr: str | None = None
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ContainerRuntimeProbeRequest(StrictModel):
    reported_phase: str | None = None
    runtime_name: str | None = None
    runtime_version: str | None = None
    engine_available: bool | None = None
    image_store_accessible: bool | None = None
    network_ready: bool | None = None
    observed_images: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class JoinCompleteRequest(StrictModel):
    reported_phase: str | None = None
    node_ref: str | None = None
    compute_node_id: str | None = None
    observed_wireguard_ip: str | None = None
    observed_advertise_addr: str | None = None
    observed_data_path_addr: str | None = None
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class CorrectionEvidenceRequest(StrictModel):
    correction_kind: str = Field(min_length=1, max_length=64)
    outcome: str = Field(min_length=1, max_length=32)
    reported_phase: str | None = None
    join_mode: str | None = None
    target_host: str | None = None
    target_port: int | None = Field(default=None, ge=1, le=65535)
    observed_wireguard_ip: str | None = None
    observed_advertise_addr: str | None = None
    observed_data_path_addr: str | None = None
    manager_node_addr_hint: str | None = None
    script_path: str | None = None
    log_path: str | None = None
    rollback_path: str | None = None
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class TcpValidationRequest(StrictModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    timeout_ms: int = Field(default=3000, ge=1, le=60000)
    validation_kind: str | None = None
    source: str | None = None
    target_label: str | None = None
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class HealthActionRequest(StrictModel):
    expected_wireguard_ip: str | None = None
    overlay_sample_count: int = Field(default=3, ge=1, le=20)
    overlay_interval_seconds: int = Field(default=1, ge=0, le=10)


class RuntimeOverlayCheckRequest(StrictModel):
    overlay_sample_count: int = Field(default=3, ge=1, le=20)
    overlay_interval_seconds: int = Field(default=1, ge=0, le=10)


class PrepareMachineWireGuardConfigRequest(StrictModel):
    source_path: str | None = None
    expected_wireguard_ip: str | None = None
    overwrite_cache: bool = False


class StandardJoinWorkflowRequest(StrictModel):
    join_mode: str = "wireguard"
    advertise_address: str | None = None
    data_path_address: str | None = None
    listen_address: str | None = None
    wireguard_config_path: str | None = None
    minimum_tcp_validation_port: int | None = Field(default=None, ge=1, le=65535)


class ManagerTaskExecutionRequest(StrictModel):
    task_probe_timeout_seconds: int = Field(default=60, ge=5, le=600)
    task_probe_interval_seconds: int = Field(default=3, ge=1, le=30)
    task_probe_image: str | None = None


class GuidedJoinAssessmentRequest(StrictModel):
    join_mode: str = "wireguard"
    expected_wireguard_ip: str | None = None
    wireguard_config_path: str | None = None
    overwrite_cache: bool = False
    overlay_sample_count: int = Field(default=2, ge=1, le=20)
    overlay_interval_seconds: int = Field(default=1, ge=0, le=10)
    post_join_probe_count: int = Field(default=8, ge=0, le=60)
    probe_interval_seconds: int = Field(default=1, ge=0, le=10)
    manager_probe_count: int = Field(default=4, ge=0, le=30)
    manager_probe_interval_seconds: int = Field(default=2, ge=0, le=20)
    task_probe_timeout_seconds: int = Field(default=60, ge=5, le=600)
    task_probe_interval_seconds: int = Field(default=3, ge=1, le=30)
    task_probe_image: str | None = None


class ClearJoinStateRequest(StrictModel):
    leave_timeout_seconds: int = Field(default=25, ge=1, le=300)
    dry_run: bool = False
    refresh_onboarding_session: bool = True
    close_onboarding_session: bool = False
    run_environment_check_after_clear: bool = True
    clear_runtime_evidence: bool = True
    clear_last_assistant_run: bool = True
    overlay_sample_count: int = Field(default=2, ge=1, le=20)
    overlay_interval_seconds: int = Field(default=1, ge=0, le=10)


class BackendCorrectionRequest(StrictModel):
    reported_phase: str | None = None
    source_surface: str | None = None
    correction_action: str = Field(min_length=1)
    target_wireguard_ip: str | None = None
    observed_advertise_addr: str | None = None
    observed_data_path_addr: str | None = None
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class BackendReverifyRequest(StrictModel):
    reported_phase: str | None = None
    node_ref: str | None = None
    compute_node_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class AuthoritativeTargetRequest(StrictModel):
    reported_phase: str | None = None
    source_surface: str | None = None
    effective_target_addr: str = Field(min_length=1)
    effective_target_reason: str = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class BackendMinimumTcpValidationRequest(StrictModel):
    reported_phase: str | None = None
    target_addr: str | None = None
    target_port: int = Field(ge=1, le=65535)
    protocol: str | None = None
    reachable: bool
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


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
                "hint": "Check the local seller client logs and retry after fixing the reported issue.",
                "details": {"exception": str(exc)},
            }
        },
    )


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.post("/local-api/window-session/open")
def window_session_open() -> dict[str, Any]:
    return state.open_window_session()


@app.post("/local-api/window-session/heartbeat")
def window_session_heartbeat(request: Request) -> dict[str, Any]:
    window_session = _require_window_session(request)
    return state.heartbeat_window_session(window_session["session_id"])


@app.post("/local-api/window-session/close")
def window_session_close(request: Request) -> dict[str, Any]:
    current = state.current_window_session()
    if current is None:
        return {"status": "already_closed"}

    window_session = _require_window_session(request)
    _close_active_onboarding(best_effort=True)
    closed = state.close_window_session(window_session["session_id"])
    return {"status": "closed", "window_session": closed}


@app.post("/local-api/auth/register")
def local_register(payload: RegisterRequest) -> dict[str, Any]:
    client = BackendClient(settings)
    try:
        response = client.register(payload.email, payload.display_name, payload.password, role=payload.role)
    except BackendClientError as exc:
        raise _backend_error(
            "auth.register",
            exc,
            message="Failed to register the seller account on the backend.",
            hint="Check backend connectivity and confirm the email is not already registered.",
        ) from exc
    state.set_auth(response["access_token"], response["user"], response.get("expires_at"))
    return {
        "user": response["user"],
        "expires_at": response["expires_at"],
    }


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
            hint="Confirm backend URL, seller account, password, and outbound HTTPS connectivity.",
        ) from exc
    state.set_auth(response["access_token"], response["user"], response.get("expires_at"))
    return {
        "user": response["user"],
        "expires_at": response["expires_at"],
    }


@app.get("/local-api/auth/me")
def local_auth_me(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        response = client.me()
    except BackendClientError as exc:
        raise _backend_error(
            "auth.me",
            exc,
            message="Failed to read the current backend seller profile.",
            hint="Refresh the seller login or retry after backend connectivity is restored.",
        ) from exc
    if isinstance(response.get("user"), dict):
        state.update_current_user(response["user"])
        return {"user": response["user"]}
    state.update_current_user(response)
    return {"user": response}


@app.get("/local-api/system/health")
def system_health(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    return {
        "local_health_snapshot": state.current_local_health_snapshot(),
        "report_path": str(settings.health_root_path / "latest-health-report.json"),
    }


@app.post("/local-api/system/check")
def system_check(payload: HealthActionRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    job = state.jobs.submit(
        "system_check",
        lambda: {
            "local_health_snapshot": state.record_local_health_snapshot(
                collect_environment_health(
                    settings,
                    expected_wireguard_ip=payload.expected_wireguard_ip or _current_expected_wireguard_ip(),
                    repair=False,
                    local_app_port=settings.app_port,
                    overlay_sample_count=payload.overlay_sample_count,
                    overlay_interval_seconds=payload.overlay_interval_seconds,
                )
            )
        },
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/system/repair")
def system_repair(payload: HealthActionRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    job = state.jobs.submit(
        "system_repair",
        lambda: {
            "local_health_snapshot": state.record_local_health_snapshot(
                collect_environment_health(
                    settings,
                    expected_wireguard_ip=payload.expected_wireguard_ip or _current_expected_wireguard_ip(),
                    repair=True,
                    local_app_port=settings.app_port,
                    overlay_sample_count=payload.overlay_sample_count,
                    overlay_interval_seconds=payload.overlay_interval_seconds,
                )
            )
        },
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/system/export-diagnostics")
def system_export_diagnostics(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    job = state.jobs.submit(
        "system_export_diagnostics",
        lambda: export_diagnostics_bundle(
            settings,
            runtime_snapshot=state.runtime_snapshot(),
            onboarding_session=state.current_onboarding_session(),
        ),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/onboarding/start")
def onboarding_start(payload: OnboardingStartRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    expected_wireguard_ip = payload.expected_wireguard_ip or settings.default_expected_wireguard_ip
    try:
        session_payload = client.create_onboarding_session(
            requested_accelerator=payload.requested_accelerator,
            requested_compute_node_id=payload.requested_compute_node_id,
            requested_offer_tier=payload.requested_offer_tier,
            expected_wireguard_ip=expected_wireguard_ip,
        )
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.start",
            exc,
            message="Failed to create the seller onboarding session.",
            hint="Confirm backend connectivity and seller permissions, then retry.",
        ) from exc

    paths = state.set_onboarding(session_payload)
    try:
        prepare_codex_session(settings=settings, state=state, session_id=session_payload["session_id"])
    except CodexSessionError as exc:
        try:
            client.close_onboarding_session(session_payload["session_id"])
        except BackendClientError:
            pass
        state.cleanup_session(session_payload["session_id"])
        raise LocalAppError(
            step="onboarding.codex",
            code="codex_session_init_failed",
            message="Failed to initialize the session-scoped Codex environment.",
            hint="Confirm Codex CLI, the config template, and ~/.codex/auth.json exist on this machine.",
            details={"exception": str(exc)},
            status_code=500,
        ) from exc

    _start_onboarding_heartbeat()
    return {
        "session": session_payload,
        "phase1_drafts": build_phase1_drafts_from_session(session_payload),
        "paths": {
            "session_root": str(paths.session_root),
            "session_file": str(paths.session_file),
            "logs_dir": str(paths.logs_dir),
            "workspace_dir": str(paths.workspace_dir),
        },
    }


@app.post("/local-api/onboarding/attach")
def onboarding_attach(payload: OnboardingAttachRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    current = state.current_onboarding_session()
    if current is not None and current["session_id"] != payload.session_id:
        _close_active_onboarding(best_effort=True)

    client = _require_backend_client()
    try:
        session_payload = client.get_onboarding_session(payload.session_id)
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.attach",
            exc,
            message="Failed to attach the stored onboarding session.",
            hint="Check the saved session id and confirm the session still exists on the backend.",
        ) from exc

    paths = state.set_onboarding(session_payload)
    try:
        prepare_codex_session(settings=settings, state=state, session_id=session_payload["session_id"])
    except CodexSessionError as exc:
        state.cleanup_session(session_payload["session_id"])
        raise LocalAppError(
            step="onboarding.attach.codex",
            code="codex_session_init_failed",
            message="Failed to reattach the local Codex session for the stored onboarding session.",
            hint="Confirm Codex CLI, the config template, and ~/.codex/auth.json exist on this machine.",
            details={"exception": str(exc)},
            status_code=500,
        ) from exc

    _start_onboarding_heartbeat()
    return {
        "session": session_payload,
        "phase1_drafts": build_phase1_drafts_from_session(session_payload),
        "paths": {
            "session_root": str(paths.session_root),
            "session_file": str(paths.session_file),
            "logs_dir": str(paths.logs_dir),
            "workspace_dir": str(paths.workspace_dir),
        },
    }


@app.get("/local-api/onboarding/current")
def onboarding_current(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    return state.runtime_snapshot()


@app.get("/local-api/onboarding/join-material")
def onboarding_join_material(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    session_payload = _require_onboarding_session()
    return {
        "session_id": session_payload.get("session_id"),
        "expected_wireguard_ip": session_payload.get("expected_wireguard_ip"),
        "manager_acceptance": session_payload.get("manager_acceptance") or {},
        "effective_target_addr": session_payload.get("effective_target_addr"),
        "effective_target_source": session_payload.get("effective_target_source"),
        "truth_authority": session_payload.get("truth_authority"),
        "minimum_tcp_validation": session_payload.get("minimum_tcp_validation") or {},
        "swarm_join_material": session_payload.get("swarm_join_material") or {},
        "required_labels": session_payload.get("required_labels") or {},
    }


@app.post("/local-api/onboarding/refresh")
def onboarding_refresh(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.get_onboarding_session(session_payload["session_id"])
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.refresh",
            exc,
            message="Failed to refresh the onboarding session from the backend.",
            hint="Check backend connectivity and confirm the onboarding session is still active.",
        ) from exc
    state.update_onboarding_session(updated)
    return state.runtime_snapshot()


@app.post("/local-api/runtime/overlay-check")
def runtime_overlay_check(payload: RuntimeOverlayCheckRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    job = state.jobs.submit(
        "runtime_overlay_check",
        lambda: state.record_runtime_workflow_result(
            {
                "kind": "overlay_runtime_check",
                "checked_at": _iso_now(),
                "result": run_overlay_runtime_check(
                    settings,
                    local_app_port=settings.app_port,
                    overlay_sample_count=payload.overlay_sample_count,
                    overlay_interval_seconds=payload.overlay_interval_seconds,
                ),
            }
        ),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/runtime/prepare-wireguard-config")
def runtime_prepare_wireguard_config(payload: PrepareMachineWireGuardConfigRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    _require_onboarding_session()
    job = state.jobs.submit(
        "runtime_prepare_wireguard_config",
        lambda: _run_prepare_machine_wireguard_config_job(payload),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/runtime/join-workflow")
def runtime_join_workflow(payload: StandardJoinWorkflowRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    session_payload = _require_onboarding_session()
    job = state.jobs.submit(
        "runtime_join_workflow",
        lambda: _run_standard_join_workflow_job(session_payload["session_id"], payload),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/runtime/guided-join-assessment")
def runtime_guided_join_assessment(payload: GuidedJoinAssessmentRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    session_payload = _require_onboarding_session()
    job = state.jobs.submit(
        "runtime_guided_join_assessment",
        lambda: _run_guided_join_assessment_job(session_payload["session_id"], payload),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/runtime/verify-manager-task-execution")
def runtime_verify_manager_task_execution(payload: ManagerTaskExecutionRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    _require_onboarding_session()
    job = state.jobs.submit(
        "runtime_verify_manager_task_execution",
        lambda: _run_verify_manager_task_execution_job(payload),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.post("/local-api/runtime/clear-join-state")
def runtime_clear_join_state(payload: ClearJoinStateRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    _require_onboarding_session()
    job = state.jobs.submit(
        "runtime_clear_join_state",
        lambda: _run_clear_join_state_job(payload),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.get("/local-api/onboarding/phase1-drafts")
def onboarding_phase1_drafts(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    return build_phase1_drafts_from_session(_require_onboarding_session())


@app.post("/local-api/onboarding/probes/linux-host")
def submit_linux_host_probe(payload: LinuxHostProbeRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.submit_linux_host_probe(session_payload["session_id"], _compact_model(payload))
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.linux_host_probe",
            exc,
            message="Failed to submit the Linux host probe.",
            hint="Check the payload shape against the current onboarding contract, then retry.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/onboarding/probes/linux-substrate")
def submit_linux_substrate_probe(payload: LinuxSubstrateProbeRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.submit_linux_substrate_probe(session_payload["session_id"], _compact_model(payload))
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.linux_substrate_probe",
            exc,
            message="Failed to submit the Linux substrate probe.",
            hint="Check the reported fields and retry after correcting the payload.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/onboarding/probes/container-runtime")
def submit_container_runtime_probe(payload: ContainerRuntimeProbeRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.submit_container_runtime_probe(session_payload["session_id"], _compact_model(payload))
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.container_runtime_probe",
            exc,
            message="Failed to submit the container runtime probe.",
            hint="Confirm the runtime probe values and retry.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/onboarding/join-complete")
def submit_join_complete(payload: JoinCompleteRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.submit_join_complete(session_payload["session_id"], _compact_model(payload))
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.join_complete",
            exc,
            message="Failed to submit join-complete to the backend.",
            hint="Provide compute_node_id or node_ref and ensure the payload stays flat.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/onboarding/correction")
def record_runtime_correction(payload: CorrectionEvidenceRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    _require_onboarding_session()
    try:
        return state.record_correction_evidence(_compact_model(payload))
    except ValueError as exc:
        raise LocalAppError(
            step="onboarding.correction",
            code="correction_payload_invalid",
            message="Failed to record local correction evidence.",
            hint="Provide the correction kind, outcome, and any local address facts before retrying.",
            details={"exception": str(exc)},
            status_code=400,
        ) from exc


@app.post("/local-api/onboarding/tcp-validation")
def run_minimum_tcp_validation(payload: TcpValidationRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    _require_onboarding_session()
    try:
        return state.record_tcp_validation(_compact_model(payload))
    except ValueError as exc:
        raise LocalAppError(
            step="onboarding.tcp_validation",
            code="tcp_validation_payload_invalid",
            message="Failed to run the local minimum TCP validation.",
            hint="Provide a reachable host, port, and timeout before retrying.",
            details={"exception": str(exc)},
            status_code=400,
        ) from exc


@app.post("/local-api/onboarding/backend/correction")
def submit_backend_correction(payload: BackendCorrectionRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.submit_correction(session_payload["session_id"], _compact_model(payload))
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.backend_correction",
            exc,
            message="Failed to submit backend correction evidence.",
            hint="Refresh the onboarding session and retry after confirming the correction payload.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/onboarding/backend/reverify")
def submit_backend_reverify(payload: BackendReverifyRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.reverify_manager_acceptance(session_payload["session_id"], _compact_model(payload))
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.backend_reverify",
            exc,
            message="Failed to reverify manager acceptance from the backend.",
            hint="Confirm the node locator fields and retry.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/onboarding/backend/authoritative-target")
def submit_authoritative_target(payload: AuthoritativeTargetRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.submit_authoritative_effective_target(session_payload["session_id"], _compact_model(payload))
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.authoritative_target",
            exc,
            message="Failed to submit the authoritative effective target to the backend.",
            hint="Confirm the target address and reason, then retry.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/onboarding/backend/minimum-tcp-validation")
def submit_backend_minimum_tcp_validation(payload: BackendMinimumTcpValidationRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    session_payload = _require_onboarding_session()
    try:
        updated = client.submit_minimum_tcp_validation(session_payload["session_id"], _compact_model(payload))
    except BackendClientError as exc:
        raise _backend_error(
            "onboarding.backend_minimum_tcp_validation",
            exc,
            message="Failed to submit the backend minimum TCP validation result.",
            hint="Confirm the effective target and TCP reachability fields, then retry.",
        ) from exc
    state.update_onboarding_session(updated)
    return updated


@app.post("/local-api/assistant/message")
def assistant_message(payload: AssistantMessageRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    session_payload = _require_onboarding_session()
    job = state.jobs.submit(
        "assistant_message",
        lambda: execute_assistant_request(
            settings=settings,
            state=state,
            session_id=session_payload["session_id"],
            user_message=payload.message,
        ),
    )
    return {"job_id": job.job_id, "status": job.status}


@app.get("/local-api/jobs/{job_id}")
def job_status(job_id: str, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    record = state.jobs.get(job_id)
    if record is None:
        raise LocalAppError(
            step="jobs.status",
            code="job_not_found",
            message="Job was not found.",
            hint="Refresh the page and rerun the action if the local job record was lost.",
            status_code=404,
        )
    return record.to_dict()


@app.post("/local-api/onboarding/close")
def onboarding_close(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    result = _close_active_onboarding(best_effort=False)
    return {"status": "closed", "session": result, "snapshot": state.runtime_snapshot()}


@app.get("/local-api/mcp/{session_id}")
def mcp_http_get(session_id: str, request: Request) -> Response:
    return _mcp_http_response(
        build_mcp_http_get_response(
            settings=settings,
            session_id=session_id,
            headers=dict(request.headers),
        )
    )


@app.post("/local-api/mcp/{session_id}")
async def mcp_http_post(session_id: str, request: Request) -> Response:
    return _mcp_http_response(
        build_mcp_http_post_response(
            settings=settings,
            session_id=session_id,
            headers=dict(request.headers),
            body=await request.body(),
        )
    )


@app.delete("/local-api/mcp/{session_id}")
def mcp_http_delete(session_id: str, request: Request) -> Response:
    return _mcp_http_response(
        build_mcp_http_delete_response(
            settings=settings,
            session_id=session_id,
            headers=dict(request.headers),
        )
    )


def _require_window_session(request: Request) -> dict[str, Any]:
    return state.require_window_session(request.headers.get("X-Window-Session-Id"))


def _mcp_http_response(payload: McpHttpResponse) -> Response:
    if payload.body is None:
        return Response(status_code=payload.status_code, headers=payload.headers)
    if isinstance(payload.body, str):
        return Response(
            status_code=payload.status_code,
            content=payload.body,
            headers=payload.headers,
            media_type=payload.media_type or "text/plain",
        )
    return JSONResponse(
        status_code=payload.status_code,
        content=payload.body,
        headers=payload.headers,
        media_type=payload.media_type or "application/json",
    )


def _require_backend_client() -> BackendClient:
    token = state.auth_token()
    if token is None:
        raise LocalAppError(
            step="auth",
            code="auth_required",
            message="Seller login is required before calling the local onboarding shell.",
            hint="Log in from the seller client first.",
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
            hint="Start a seller onboarding session before using this action.",
            status_code=409,
        )
    return session_payload


def _run_standard_join_workflow_job(session_id: str, payload: StandardJoinWorkflowRequest) -> dict[str, Any]:
    session_file = state.write_session_runtime_file()
    if session_file is None:
        raise LocalAppError(
            step="runtime.join_workflow",
            code="session_file_missing",
            message="The local onboarding session file is not available.",
            hint="Refresh the onboarding session and retry the standard join workflow.",
            status_code=409,
        )

    health_snapshot = collect_environment_health(
        settings,
        expected_wireguard_ip=_current_expected_wireguard_ip(),
        repair=False,
        local_app_port=settings.app_port,
        overlay_sample_count=2,
        overlay_interval_seconds=1,
    )
    state.record_local_health_snapshot(health_snapshot)

    expected_wireguard_ip = payload.advertise_address or _current_expected_wireguard_ip()
    wireguard_config_preparation = prepare_machine_wireguard_config(
        settings,
        source_path=payload.wireguard_config_path,
        expected_wireguard_ip=expected_wireguard_ip,
    )

    workflow_result = run_standard_join_workflow(
        settings,
        session_file=str(session_file),
        join_mode=payload.join_mode,
        advertise_address=expected_wireguard_ip,
        data_path_address=payload.data_path_address or payload.advertise_address or _current_expected_wireguard_ip(),
        listen_address=payload.listen_address,
        wireguard_config_path=payload.wireguard_config_path,
    )

    refreshed_session: dict[str, Any] | None = None
    try:
        refreshed_session = _require_backend_client().get_onboarding_session(session_id)
        state.update_onboarding_session(refreshed_session)
    except BackendClientError:
        refreshed_session = state.current_onboarding_session()

    recorded = state.record_runtime_workflow_result(
        {
            "kind": "standard_join_workflow",
            "ran_at": _iso_now(),
            "workflow": workflow_result,
            "wireguard_config_preparation": wireguard_config_preparation,
            "session_id": session_id,
        }
    )
    return {
        "workflow": recorded,
        "onboarding_session": refreshed_session,
        "local_health_snapshot": state.current_local_health_snapshot(),
    }


def _run_prepare_machine_wireguard_config_job(payload: PrepareMachineWireGuardConfigRequest) -> dict[str, Any]:
    expected_wireguard_ip = payload.expected_wireguard_ip or _current_expected_wireguard_ip()
    result = prepare_machine_wireguard_config(
        settings,
        source_path=payload.source_path,
        expected_wireguard_ip=expected_wireguard_ip,
        overwrite_cache=payload.overwrite_cache,
    )
    recorded = state.record_runtime_workflow_result(
        {
            "kind": "prepare_machine_wireguard_config",
            "ran_at": _iso_now(),
            "result": result,
            "expected_wireguard_ip": expected_wireguard_ip,
        }
    )
    return {"workflow": recorded}


def _run_verify_manager_task_execution_job(payload: ManagerTaskExecutionRequest) -> dict[str, Any]:
    session_file = state.write_session_runtime_file()
    if session_file is None:
        raise LocalAppError(
            step="runtime.verify_manager_task_execution",
            code="session_file_missing",
            message="The local onboarding session file is not available.",
            hint="Refresh the onboarding session and retry manager task verification.",
            status_code=409,
        )

    result = verify_manager_task_execution(
        settings,
        session_file=str(session_file),
        task_probe_timeout_seconds=payload.task_probe_timeout_seconds,
        task_probe_interval_seconds=payload.task_probe_interval_seconds,
        probe_image=payload.task_probe_image,
    )
    recorded = state.record_runtime_workflow_result(
        {
            "kind": "verify_manager_task_execution",
            "ran_at": _iso_now(),
            "result": result,
        }
    )
    return {"workflow": recorded}


def _run_guided_join_assessment_job(session_id: str, payload: GuidedJoinAssessmentRequest) -> dict[str, Any]:
    session_file = state.write_session_runtime_file()
    if session_file is None:
        raise LocalAppError(
            step="runtime.guided_join_assessment",
            code="session_file_missing",
            message="The local onboarding session file is not available.",
            hint="Refresh the onboarding session and retry the guided join assessment.",
            status_code=409,
        )

    expected_wireguard_ip = payload.expected_wireguard_ip or _current_expected_wireguard_ip()
    wireguard_config_result = prepare_machine_wireguard_config(
        settings,
        source_path=payload.wireguard_config_path,
        expected_wireguard_ip=expected_wireguard_ip,
        overwrite_cache=payload.overwrite_cache,
    )

    local_health_snapshot = collect_environment_health(
        settings,
        expected_wireguard_ip=expected_wireguard_ip,
        repair=False,
        local_app_port=settings.app_port,
        overlay_sample_count=payload.overlay_sample_count,
        overlay_interval_seconds=payload.overlay_interval_seconds,
    )
    state.record_local_health_snapshot(local_health_snapshot)

    if wireguard_config_result.get("ok"):
        workflow_result = run_standard_join_workflow(
            settings,
            session_file=str(session_file),
            join_mode=payload.join_mode,
            advertise_address=expected_wireguard_ip,
            data_path_address=expected_wireguard_ip,
            listen_address=None,
            wireguard_config_path=wireguard_config_result.get("target_path"),
            post_join_probe_count=payload.post_join_probe_count,
            probe_interval_seconds=payload.probe_interval_seconds,
            manager_probe_count=payload.manager_probe_count,
            manager_probe_interval_seconds=payload.manager_probe_interval_seconds,
        )
    else:
        workflow_result = {
            "ok": False,
            "step": "standard_join_workflow",
            "error": str(wireguard_config_result.get("error") or "machine_wireguard_config_missing"),
            "payload": None,
            "wireguard_config_preparation": wireguard_config_result,
        }

    refreshed_session: dict[str, Any] | None = None
    try:
        refreshed_session = _require_backend_client().get_onboarding_session(session_id)
        state.update_onboarding_session(refreshed_session)
    except BackendClientError:
        refreshed_session = state.current_onboarding_session()

    if workflow_result.get("ok"):
        manager_task_execution = verify_manager_task_execution(
            settings,
            session_file=str(session_file),
            task_probe_timeout_seconds=payload.task_probe_timeout_seconds,
            task_probe_interval_seconds=payload.task_probe_interval_seconds,
            probe_image=payload.task_probe_image,
        )
    else:
        manager_task_execution = {
            "ok": False,
            "step": "manager_task_execution",
            "error": "skipped_until_join_succeeds",
            "payload": {
                "completion_standard": "manager_task_execution",
                "task_execution_verified": False,
                "status": "skipped",
                "reason": "join_workflow_not_successful",
            },
        }

    join_effect = _summarize_guided_join_effect(workflow_result, refreshed_session or {}, manager_task_execution)
    recorded = state.record_runtime_workflow_result(
        {
            "kind": "guided_join_assessment",
            "ran_at": _iso_now(),
            "wireguard_config_preparation": wireguard_config_result,
            "join_workflow": workflow_result,
            "manager_task_execution": manager_task_execution,
            "join_effect": join_effect,
            "session_id": session_id,
        }
    )
    return {
        "workflow": recorded,
        "wireguard_config_preparation": wireguard_config_result,
        "local_health_snapshot": state.current_local_health_snapshot(),
        "join_workflow": workflow_result,
        "manager_task_execution": manager_task_execution,
        "join_effect": join_effect,
        "onboarding_session": refreshed_session,
    }


def _run_clear_join_state_job(payload: ClearJoinStateRequest) -> dict[str, Any]:
    session_payload = _require_onboarding_session()
    clear_result = perform_clear_join_state(
        settings,
        leave_timeout_seconds=payload.leave_timeout_seconds,
        dry_run=payload.dry_run,
    )

    refreshed_session = session_payload
    backend_sync = {"attempted": False, "status": "skipped", "reason": None}
    if state.auth_token():
        if payload.close_onboarding_session:
            try:
                refreshed_session = _require_backend_client().close_onboarding_session(session_payload["session_id"])
                state.update_onboarding_session(refreshed_session)
                backend_sync = {"attempted": True, "status": "closed", "reason": None}
            except BackendClientError as exc:
                raise _backend_error(
                    "runtime.clear_join_state.close",
                    exc,
                    message="Failed to close the onboarding session while clearing local join state.",
                    hint="Retry the local clear or close the backend onboarding session separately.",
                ) from exc
        elif payload.refresh_onboarding_session:
            try:
                refreshed_session = _require_backend_client().get_onboarding_session(session_payload["session_id"])
                state.update_onboarding_session(refreshed_session)
                backend_sync = {"attempted": True, "status": "refreshed", "reason": None}
            except BackendClientError as exc:
                raise _backend_error(
                    "runtime.clear_join_state.refresh",
                    exc,
                    message="Failed to refresh the onboarding session after clearing local join state.",
                    hint="Retry after backend connectivity is restored, or disable refresh if you only need a local clear.",
                ) from exc
    elif payload.close_onboarding_session or payload.refresh_onboarding_session:
        backend_sync = {"attempted": False, "status": "skipped", "reason": "auth_required"}

    local_health_snapshot = state.current_local_health_snapshot()
    if payload.run_environment_check_after_clear:
        local_health_snapshot = collect_environment_health(
            settings,
            expected_wireguard_ip=_current_expected_wireguard_ip(),
            repair=False,
            local_app_port=settings.app_port,
            overlay_sample_count=payload.overlay_sample_count,
            overlay_interval_seconds=payload.overlay_interval_seconds,
        )

    workflow_record = {
        "kind": "clear_join_state",
        "ran_at": _iso_now(),
        "session_id": session_payload["session_id"],
        "result": clear_result,
    }
    snapshot = state.reset_join_state(
        runtime_workflow=workflow_record,
        local_health_snapshot=local_health_snapshot,
        clear_runtime_evidence=payload.clear_runtime_evidence,
        clear_last_assistant_run=payload.clear_last_assistant_run,
    )

    if not clear_result.get("ok"):
        raise LocalAppError(
            step="runtime.clear_join_state",
            code="clear_join_state_failed",
            message="Failed to clear the local Windows join state.",
            hint="Inspect the clear_join_state result and Docker Swarm state, then retry after resolving the reported issue.",
            details=clear_result,
            status_code=500,
        )

    return {
        "clear_join_state": clear_result,
        "backend_sync": backend_sync,
        "onboarding_session": refreshed_session,
        "local_health_snapshot": snapshot.get("local_health_snapshot"),
        "runtime_evidence": snapshot.get("runtime_evidence"),
        "last_runtime_workflow": snapshot.get("last_runtime_workflow"),
    }


def _current_expected_wireguard_ip() -> str | None:
    session = state.current_onboarding_session()
    if session is None:
        return settings.default_expected_wireguard_ip
    return session.get("expected_wireguard_ip") or settings.default_expected_wireguard_ip


def _summarize_guided_join_effect(
    workflow_result: dict[str, Any],
    refreshed_onboarding: dict[str, Any],
    manager_task_execution: dict[str, Any],
) -> dict[str, Any]:
    workflow_payload = dict(workflow_result.get("payload") or {})
    workflow_summary = dict(workflow_payload.get("summary") or {})
    join_result = dict(workflow_payload.get("join_result") or {})
    manager_acceptance = dict(refreshed_onboarding.get("manager_acceptance") or {})
    task_payload = dict(manager_task_execution.get("payload") or {})

    after_state_raw = join_result.get("after_state")
    after_state: dict[str, Any] = {}
    if isinstance(after_state_raw, str) and after_state_raw.strip():
        try:
            parsed = json.loads(after_state_raw)
            if isinstance(parsed, dict):
                after_state = parsed
        except ValueError:
            after_state = {}
    elif isinstance(after_state_raw, dict):
        after_state = dict(after_state_raw)

    return {
        "success_standard": "manager_task_execution",
        "swarm_connectivity": {
            "verified": workflow_summary.get("swarm_connectivity_verified"),
            "local_swarm_active": workflow_summary.get("local_swarm_active"),
            "manager_acceptance_matched": workflow_summary.get("manager_acceptance_matched"),
            "path_outcome": workflow_summary.get("path_outcome"),
        },
        "manager_task_execution": {
            "verified": manager_task_execution.get("ok"),
            "status": task_payload.get("status"),
            "proof_source": task_payload.get("proof_source"),
            "selected_node_id": ((task_payload.get("selected_candidate") or {}).get("id")),
        },
        "local_join": {
            "ok": workflow_result.get("ok"),
            "path_outcome": workflow_summary.get("path_outcome"),
            "local_node_state": after_state.get("LocalNodeState"),
            "local_node_id": after_state.get("NodeID"),
            "local_node_addr": after_state.get("NodeAddr"),
            "join_idempotent_reason": join_result.get("join_idempotent_reason"),
        },
        "manager_raw_truth": {
            "status": manager_acceptance.get("status"),
            "observed_manager_node_addr": manager_acceptance.get("observed_manager_node_addr"),
            "matched": manager_acceptance.get("matched"),
            "detail": manager_acceptance.get("detail"),
        },
        "backend_authoritative_target": {
            "effective_target_addr": refreshed_onboarding.get("effective_target_addr"),
            "effective_target_source": refreshed_onboarding.get("effective_target_source"),
            "truth_authority": refreshed_onboarding.get("truth_authority"),
            "session_status": refreshed_onboarding.get("status"),
        },
    }


def _close_active_onboarding(*, best_effort: bool) -> dict[str, Any] | None:
    session_payload = state.current_onboarding_session()
    if session_payload is None:
        return None
    cleanup_needed = best_effort
    try:
        if state.auth_token():
            client = _require_backend_client()
            session_payload = client.close_onboarding_session(session_payload["session_id"])
        cleanup_needed = True
    except BackendClientError as exc:
        if not best_effort:
            raise _backend_error(
                "onboarding.close",
                exc,
                message="Failed to close the onboarding session on the backend.",
                hint="Refresh the session and retry close after backend connectivity is restored.",
            ) from exc
    finally:
        if cleanup_needed:
            cleanup_codex_session(settings=settings, state=state, session_id=session_payload["session_id"])
    return session_payload


def _backend_error(step: str, exc: BackendClientError, *, message: str, hint: str) -> LocalAppError:
    return LocalAppError(
        step=step,
        code="backend_request_failed",
        message=message,
        hint=hint,
        details=exc.payload or {"detail": exc.detail},
        status_code=exc.status_code if 400 <= exc.status_code < 600 else 502,
    )


def _compact_model(payload: BaseModel) -> dict[str, Any]:
    return payload.model_dump(exclude_none=True)


def _iso_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _start_onboarding_heartbeat() -> None:
    def _heartbeat() -> dict[str, Any]:
        session = state.current_onboarding_session()
        if session is None:
            raise RuntimeError("Onboarding session closed.")
        updated = _require_backend_client().heartbeat_onboarding_session(session["session_id"])
        state.update_onboarding_session(updated)
        return updated

    state.start_heartbeat(_heartbeat)
