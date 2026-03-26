from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.identity import User
from app.models.platform import ImageOffer, Node, RuntimeAccessSession
from app.schemas.platform import (
    BuyerRuntimeSessionCreateRequest,
    BuyerRuntimeSessionCreateResponse,
    BuyerRuntimeSessionReportRequest,
    BuyerRuntimeSessionRenewRequest,
    BuyerRuntimeSessionRenewResponse,
    BuyerRuntimeSessionRedeemRequest,
    BuyerRuntimeSessionRedeemResponse,
    BuyerRuntimeSessionStatusResponse,
    BuyerRuntimeSessionStopResponse,
    BuyerRuntimeSessionWireGuardBootstrapRequest,
    BuyerRuntimeSessionWireGuardBootstrapResponse,
)
from app.services.activity import log_activity
from app.services.runtime_bootstrap import RuntimeBootstrapError, build_buyer_wireguard_bootstrap
from app.services.runtime_sessions import TERMINAL_SESSION_STATES, expire_runtime_session, renew_runtime_session
from app.services.swarm_manager import (
    create_shell_runtime_service,
    SwarmManagerError,
    create_code_runtime_service,
    inspect_code_runtime_service,
    remove_code_runtime_service,
)
from app.services.wireguard_server import WireGuardServerError, apply_server_peer, remove_server_peer

router = APIRouter(prefix="/buyer")


def utcnow() -> datetime:
    return datetime.utcnow()


def _runtime_session_status_from_task(task: dict) -> str:
    state = str(task.get("CurrentState") or "").lower()
    desired = str(task.get("DesiredState") or "").lower()
    if "running" in state:
        return "running"
    if "complete" in state or "shutdown" in desired:
        return "completed"
    if "failed" in state or "rejected" in state:
        return "failed"
    return "starting"


def _session_mode(session: RuntimeAccessSession) -> str:
    return "shell" if session.code_filename == "__shell__" else "code_run"


def _relay_endpoint(session_id: int) -> str:
    return f"relay://buyer-runtime-session/{session_id}"


def _placement_constraint_for_node(node: Node) -> str:
    match = re.search(r"node_id=([a-z0-9]+)", node.swarm_state or "", re.IGNORECASE)
    if match:
        return f"node.id=={match.group(1)}"
    return f"node.hostname=={node.hostname}"


def _runtime_callback_base_url(request: Request) -> str:
    parts = urlsplit(str(request.base_url))
    hostname = parts.hostname or "127.0.0.1"
    if hostname in {"127.0.0.1", "localhost"}:
        host = "host.docker.internal"
        netloc = f"{host}:{parts.port}" if parts.port else host
        return urlunsplit((parts.scheme, netloc, "", "", "")).rstrip("/")
    return str(request.base_url).rstrip("/")


def _get_runtime_session_for_buyer(db: Session, session_id: int, buyer_id: int) -> RuntimeAccessSession | None:
    statement = select(RuntimeAccessSession).where(
        RuntimeAccessSession.id == session_id,
        RuntimeAccessSession.buyer_user_id == buyer_id,
    )
    return db.scalar(statement)


@router.post("/runtime-sessions", response_model=BuyerRuntimeSessionCreateResponse)
def create_buyer_runtime_session(
    payload: BuyerRuntimeSessionCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionCreateResponse:
    offer = None
    if payload.offer_id is not None:
        offer = db.get(ImageOffer, payload.offer_id)
        if offer is None or offer.offer_status != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image offer not found.")
        node = db.get(Node, offer.node_id)
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")
        runtime_image = offer.runtime_image_ref
        seller_node_key = node.node_key
    else:
        if not payload.seller_node_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="seller_node_key is required for ad hoc sessions.")
        node = db.scalar(select(Node).where(Node.node_key == payload.seller_node_key))
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")
        runtime_image = payload.runtime_image
        seller_node_key = payload.seller_node_key

    if node.status != "available":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seller node is not available.")
    if payload.session_mode not in {"code_run", "shell"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported session_mode.")
    if payload.source_type not in {"inline_code", "archive"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported source_type.")
    if payload.session_mode == "code_run" and payload.source_type == "inline_code" and not payload.code_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_content is required for inline_code mode.")
    if payload.session_mode == "code_run" and payload.source_type == "archive" and not payload.archive_content_base64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="archive_content_base64 is required for archive mode.")

    code_sha256 = hashlib.sha256(payload.code_content.encode("utf-8")).hexdigest() if payload.code_content else ""
    connect_code = secrets.token_urlsafe(10)
    session_token = secrets.token_urlsafe(24)
    expires_at = utcnow() + timedelta(minutes=payload.requested_duration_minutes)
    service_name = f"buyer-runtime-{secrets.token_hex(6)}"
    config_name = f"buyer-code-{secrets.token_hex(6)}"
    entry_command = payload.entry_command or (
        ["sh", "-lc", "while true; do sleep 3600; done"]
        if payload.session_mode == "shell"
        else ["python", f"/workspace/{payload.code_filename}"]
    )
    code_filename = "__shell__" if payload.session_mode == "shell" else payload.code_filename
    if payload.session_mode == "shell":
        code_sha256 = "shell-session"
    elif payload.source_type == "archive":
        code_sha256 = hashlib.sha256(payload.archive_content_base64.encode("utf-8")).hexdigest()

    session = RuntimeAccessSession(
        buyer_user_id=current_user.id,
        seller_node_id=node.id,
        image_artifact_id=offer.image_artifact_id if offer else None,
        image_offer_id=offer.id if offer else None,
        runtime_image=runtime_image,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        working_dir=payload.working_dir,
        code_filename=code_filename,
        code_sha256=code_sha256,
        service_name=service_name,
        config_name=config_name,
        connect_code=connect_code,
        session_token=session_token,
        network_mode="wireguard",
        status="created",
        command=entry_command,
        expires_at=expires_at,
        accrued_usage_cny=0.0,
    )
    db.add(session)
    db.flush()
    report_url = f"{_runtime_callback_base_url(request)}/api/v1/buyer/runtime-sessions/{session.id}/report"

    try:
        if payload.session_mode == "shell":
            create_shell_runtime_service(
                settings,
                service_name=service_name,
                placement_constraint=_placement_constraint_for_node(node),
                runtime_image=runtime_image,
                entry_command=entry_command,
            )
        else:
            create_code_runtime_service(
                settings,
                service_name=service_name,
                config_name=config_name,
                placement_constraint=_placement_constraint_for_node(node),
                runtime_image=runtime_image,
                code_filename=payload.code_filename,
                code_content=payload.code_content,
                entry_command=entry_command,
                report_url=report_url,
                session_token=session_token,
                source_type=payload.source_type,
                archive_filename=payload.archive_filename,
                archive_content_base64=payload.archive_content_base64,
                working_dir=payload.working_dir,
                run_command=payload.run_command,
            )
        inspect_result = inspect_code_runtime_service(settings, service_name=service_name)
    except SwarmManagerError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    current_task = inspect_result.get("current_task", {})
    session.status = _runtime_session_status_from_task(current_task)
    session.started_at = utcnow()
    session.last_logs = str(inspect_result.get("logs") or "")
    log_activity(
        db,
        seller_user_id=node.seller_user_id,
        node_id=node.id,
        event_type="buyer_runtime_session_created",
        summary=f"Created buyer runtime session on {node.hostname}",
        metadata={
            "session_id": session.id,
            "buyer_user_id": current_user.id,
            "runtime_image": runtime_image,
            "service_name": service_name,
            "source_type": payload.source_type,
            "offer_id": offer.id if offer else None,
        },
    )
    db.commit()
    return BuyerRuntimeSessionCreateResponse(
        session_id=session.id,
        offer_id=offer.id if offer else None,
        connect_code=connect_code,
        expires_at=expires_at,
        seller_node_key=seller_node_key,
        runtime_image=runtime_image,
        session_mode=payload.session_mode,
        source_type=payload.source_type,
    )


@router.post("/runtime-sessions/{session_id}/report")
def report_buyer_runtime_session(
    session_id: int,
    payload: BuyerRuntimeSessionReportRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    session = db.get(RuntimeAccessSession, session_id)
    if session is None or session.session_token != payload.session_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")

    session.status = payload.status
    session.last_logs = payload.logs
    if session.started_at is None:
        session.started_at = utcnow()
    if payload.status in {"completed", "failed"}:
        session.ended_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/runtime-sessions/redeem", response_model=BuyerRuntimeSessionRedeemResponse)
def redeem_buyer_runtime_session(payload: BuyerRuntimeSessionRedeemRequest, db: Session = Depends(get_db)) -> BuyerRuntimeSessionRedeemResponse:
    statement = select(RuntimeAccessSession).where(RuntimeAccessSession.connect_code == payload.connect_code)
    session = db.scalar(statement)
    if session is None or (session.expires_at and session.expires_at < utcnow()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connect code not found or expired.")

    return BuyerRuntimeSessionRedeemResponse(
        session_id=session.id,
        session_token=session.session_token,
        access_mode="relay",
        network_mode=session.network_mode,
        relay_endpoint=_relay_endpoint(session.id),
        runtime_image=session.runtime_image,
        status=session.status,
    )


@router.post("/runtime-sessions/{session_id}/wireguard/bootstrap", response_model=BuyerRuntimeSessionWireGuardBootstrapResponse)
def bootstrap_buyer_runtime_wireguard(
    session_id: int,
    payload: BuyerRuntimeSessionWireGuardBootstrapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionWireGuardBootstrapResponse:
    session = _get_runtime_session_for_buyer(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")
    if session.expires_at and session.expires_at < utcnow():
        session = expire_runtime_session(db, session)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"runtime_session_{session.status}")
    if session.status in {"stopped", "expired", "failed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"runtime_session_{session.status}")
    node = db.get(Node, session.seller_node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")

    if session.buyer_wireguard_public_key and session.buyer_wireguard_public_key != payload.client_public_key:
        try:
            remove_server_peer(settings, public_key=session.buyer_wireguard_public_key)
        except Exception:
            pass

    try:
        bundle = build_buyer_wireguard_bootstrap(settings, session, node, payload.client_public_key)
        apply_server_peer(
            settings,
            public_key=payload.client_public_key,
            client_address=bundle["client_address"],
            persistent_keepalive=bundle["persistent_keepalive"],
        )
    except RuntimeBootstrapError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except WireGuardServerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    session.buyer_wireguard_public_key = payload.client_public_key
    session.buyer_wireguard_client_address = bundle["client_address"]
    session.seller_wireguard_target = bundle.get("seller_wireguard_target")
    session.network_mode = "wireguard"
    db.commit()
    return BuyerRuntimeSessionWireGuardBootstrapResponse(**bundle)


@router.get("/runtime-sessions/{session_id}", response_model=BuyerRuntimeSessionStatusResponse)
def read_buyer_runtime_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionStatusResponse:
    session = _get_runtime_session_for_buyer(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")
    if session.expires_at and session.expires_at < utcnow() and session.status not in TERMINAL_SESSION_STATES:
        session = expire_runtime_session(db, session)

    should_refresh_remote = session.status not in TERMINAL_SESSION_STATES or (
        session.status in {"completed", "failed"} and not session.last_logs
    )
    if should_refresh_remote:
        try:
            inspect_result = inspect_code_runtime_service(settings, service_name=session.service_name)
            current_task = inspect_result.get("current_task", {})
            session.status = _runtime_session_status_from_task(current_task)
            inspected_logs = str(inspect_result.get("logs") or "")
            if inspected_logs:
                session.last_logs = inspected_logs
            if session.status in {"completed", "failed"} and session.ended_at is None:
                session.ended_at = utcnow()
            db.commit()
        except Exception:
            # If remote inspect fails, keep the last persisted session state and logs.
            pass

    node = db.get(Node, session.seller_node_id)
    current_hourly_price = None
    if session.image_offer_id is not None:
        offer = db.get(ImageOffer, session.image_offer_id)
        if offer is not None:
            current_hourly_price = offer.current_billable_price_cny_per_hour
    return BuyerRuntimeSessionStatusResponse(
        session_id=session.id,
        offer_id=session.image_offer_id,
        seller_node_key=node.node_key if node else "",
        runtime_image=session.runtime_image,
        source_type=session.source_type,
        code_filename=session.code_filename,
        session_mode=_session_mode(session),
        network_mode=session.network_mode,
        buyer_wireguard_client_address=session.buyer_wireguard_client_address,
        seller_wireguard_target=session.seller_wireguard_target,
        status=session.status,
        service_name=session.service_name,
        relay_endpoint=_relay_endpoint(session.id),
        current_hourly_price_cny=current_hourly_price,
        accrued_usage_cny=float(session.accrued_usage_cny or 0.0),
        logs=session.last_logs or "",
        created_at=session.created_at,
        started_at=session.started_at,
        expires_at=session.expires_at,
        ended_at=session.ended_at,
    )


@router.post("/runtime-sessions/{session_id}/stop", response_model=BuyerRuntimeSessionStopResponse)
def stop_buyer_runtime_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionStopResponse:
    session = _get_runtime_session_for_buyer(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")

    try:
        remove_code_runtime_service(settings, service_name=session.service_name, config_name=session.config_name)
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if session.buyer_wireguard_public_key:
        try:
            remove_server_peer(settings, public_key=session.buyer_wireguard_public_key)
        except WireGuardServerError:
            pass

    session.status = "stopped"
    session.ended_at = utcnow()
    db.commit()
    return BuyerRuntimeSessionStopResponse(session_id=session.id, status=session.status)


@router.post("/runtime-sessions/{session_id}/renew", response_model=BuyerRuntimeSessionRenewResponse)
def renew_buyer_runtime_session(
    session_id: int,
    payload: BuyerRuntimeSessionRenewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionRenewResponse:
    session = _get_runtime_session_for_buyer(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")

    try:
        session = renew_runtime_session(db, session, payload.additional_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return BuyerRuntimeSessionRenewResponse(
        session_id=session.id,
        status=session.status,
        expires_at=session.expires_at,
    )
