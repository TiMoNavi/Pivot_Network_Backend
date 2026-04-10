from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from buyer_client_app.backend import BackendClient, BackendClientError
from buyer_client_app.config import get_settings
from buyer_client_app.errors import LocalAppError
from buyer_client_app.flow import build_runtime_access_plan
from buyer_client_app.state import BuyerClientState

settings = get_settings()
state = BuyerClientState(settings)
app = FastAPI(title="Pivot Buyer Client", version="0.1.0")
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
    role: str = "buyer"


class OrderCreateRequest(StrictModel):
    offer_id: str = Field(min_length=1)
    requested_duration_minutes: int = Field(default=settings.default_requested_duration_minutes, ge=1, le=24 * 60)


class AttachGrantRequest(StrictModel):
    grant_id: str | None = None


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
                "message": "Buyer client encountered an unexpected internal error.",
                "hint": "Check the local buyer client logs and retry after fixing the reported issue.",
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
            message="Failed to register the buyer account on the backend.",
            hint="Check backend connectivity and confirm the email is not already registered.",
        ) from exc
    state.set_auth(response["access_token"], response["user"], _coerce_datetime(response.get("expires_at")))
    return {"user": response["user"], "expires_at": response["expires_at"]}


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
            hint="Confirm backend URL, buyer account, password, and outbound HTTPS connectivity.",
        ) from exc
    state.set_auth(response["access_token"], response["user"], _coerce_datetime(response.get("expires_at")))
    return {"user": response["user"], "expires_at": response["expires_at"]}


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
            message="Failed to read the current backend buyer profile.",
            hint="Refresh the buyer login or retry after backend connectivity is restored.",
        ) from exc
    state.update_current_user(response)
    return {"user": response}


@app.get("/local-api/offers")
def list_offers(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        response = client.list_offers()
    except BackendClientError as exc:
        raise _backend_error(
            "offers.list",
            exc,
            message="Failed to fetch the current offer catalog.",
            hint="Check backend connectivity and retry after the catalog is available.",
        ) from exc
    items = list(response.get("items") or [])
    state.set_offers(items)
    return {"items": items, "total": response.get("total", len(items))}


@app.get("/local-api/offers/{offer_id}")
def get_offer(offer_id: str, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        return client.get_offer(offer_id)
    except BackendClientError as exc:
        raise _backend_error(
            "offers.get",
            exc,
            message="Failed to fetch the selected offer.",
            hint="Confirm the offer still exists and retry.",
        ) from exc


@app.post("/local-api/orders")
def create_order(payload: OrderCreateRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        order = client.create_order(payload.offer_id, payload.requested_duration_minutes)
    except BackendClientError as exc:
        raise _backend_error(
            "orders.create",
            exc,
            message="Failed to create the buyer order.",
            hint="Confirm the selected offer is still available and retry.",
        ) from exc
    runtime_plan = build_runtime_access_plan(order, None)
    state.set_current_order(order, runtime_plan)
    return {"order": order, "runtime_access_plan": runtime_plan}


@app.get("/local-api/orders/{order_id}")
def get_order(order_id: str, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        return client.get_order(order_id)
    except BackendClientError as exc:
        raise _backend_error(
            "orders.get",
            exc,
            message="Failed to fetch the buyer order.",
            hint="Confirm the order still exists for the current buyer and retry.",
        ) from exc


@app.post("/local-api/orders/{order_id}/activate")
def activate_order(order_id: str, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        activation = client.activate_order(order_id)
    except BackendClientError as exc:
        raise _backend_error(
            "orders.activate",
            exc,
            message="Failed to activate the buyer order.",
            hint="Retry after the platform has finished allocating the runtime bundle.",
        ) from exc
    order = dict(activation["order"])
    access_grant = dict(activation["access_grant"])
    runtime_plan = build_runtime_access_plan(order, access_grant)
    state.set_activation(order, access_grant, runtime_plan)
    return {
        "order": order,
        "access_grant": access_grant,
        "runtime_access_plan": runtime_plan,
    }


@app.get("/local-api/access-grants/active")
def active_access_grants(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        response = client.list_active_access_grants()
    except BackendClientError as exc:
        raise _backend_error(
            "access_grants.active",
            exc,
            message="Failed to read the buyer's active access grants.",
            hint="Retry after backend connectivity is restored.",
        ) from exc
    items = list(response.get("items") or [])
    state.set_active_access_grants(items)
    return {"items": items, "total": response.get("total", len(items))}


@app.post("/local-api/runtime/attach-active-grant")
def attach_active_grant(payload: AttachGrantRequest, request: Request) -> dict[str, Any]:
    _require_window_session(request)
    client = _require_backend_client()
    try:
        response = client.list_active_access_grants()
    except BackendClientError as exc:
        raise _backend_error(
            "runtime.attach",
            exc,
            message="Failed to read active grants while attaching the buyer runtime session.",
            hint="Retry after backend connectivity is restored.",
        ) from exc
    items = list(response.get("items") or [])
    state.set_active_access_grants(items)
    grant = _select_active_grant(items, payload.grant_id)
    try:
        order = client.get_order(grant["order_id"])
    except BackendClientError as exc:
        raise _backend_error(
            "runtime.attach.order",
            exc,
            message="Active grant exists, but its order could not be loaded.",
            hint="Retry after backend order state is readable again.",
        ) from exc
    runtime_plan = build_runtime_access_plan(order, grant)
    state.set_activation(order, grant, runtime_plan)
    return {
        "order": order,
        "access_grant": grant,
        "runtime_access_plan": runtime_plan,
    }


@app.get("/local-api/runtime/access-plan")
def runtime_access_plan(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    plan = build_runtime_access_plan(state.current_order(), state.current_access_grant())
    return {"runtime_access_plan": plan}


@app.get("/local-api/runtime/current")
def runtime_current(request: Request) -> dict[str, Any]:
    _require_window_session(request)
    return state.runtime_snapshot()


def _require_window_session(request: Request) -> dict[str, Any]:
    return state.require_window_session(request.headers.get("X-Window-Session-Id"))


def _require_backend_client() -> BackendClient:
    token = state.auth_token()
    if not token:
        raise LocalAppError(
            step="auth",
            code="auth_session_missing",
            message="Buyer backend login is missing.",
            hint="Log in from the buyer client before performing platform actions.",
            status_code=401,
        )
    return BackendClient(settings, token=token)


def _select_active_grant(items: list[dict[str, Any]], grant_id: str | None) -> dict[str, Any]:
    if not items:
        raise LocalAppError(
            step="runtime.attach",
            code="active_grant_missing",
            message="No active access grant is available for the current buyer.",
            hint="Activate an order first, then attach the active runtime grant.",
            status_code=409,
        )
    if grant_id:
        for item in items:
            if item.get("id") == grant_id:
                return dict(item)
        raise LocalAppError(
            step="runtime.attach",
            code="grant_not_found",
            message="The requested active grant was not found.",
            hint="Refresh the active grant list and retry with a current grant id.",
            status_code=404,
        )
    return dict(items[0])


def _backend_error(step: str, exc: BackendClientError, *, message: str, hint: str) -> LocalAppError:
    return LocalAppError(
        step=step,
        code="backend_request_failed",
        message=message,
        hint=hint,
        details={
            "status_code": exc.status_code,
            "backend_detail": exc.detail,
            "payload": exc.payload,
        },
        status_code=502 if exc.status_code >= 500 else exc.status_code,
    )


def _coerce_datetime(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
