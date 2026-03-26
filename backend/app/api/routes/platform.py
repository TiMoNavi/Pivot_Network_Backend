from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_node_token, get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.activity import ActivityEvent
from app.models.identity import NodeRegistrationToken, User
from app.models.platform import ImageArtifact, Node
from app.schemas.activity import ActivityEventResponse
from app.schemas.platform import (
    ImageArtifactResponse,
    ImageReportRequest,
    IssueNodeTokenRequest,
    CodexRuntimeBootstrapResponse,
    NodeHeartbeatRequest,
    NodeRegisterRequest,
    NodeResponse,
    NodeTokenListResponse,
    NodeTokenResponse,
    PlatformOverviewResponse,
    SwarmRemoteOverviewResponse,
    SwarmWorkerJoinTokenResponse,
    WireGuardBootstrapRequest,
    WireGuardBootstrapResponse,
)
from app.services.activity import log_activity
from app.services.auth import issue_node_registration_token
from app.services.image_offer_publishing import run_offer_probe_and_pricing
from app.services.pricing_engine import PricingEngineError
from app.services.runtime_bootstrap import (
    RuntimeBootstrapError,
    build_codex_runtime_bootstrap,
    build_wireguard_bootstrap,
)
from app.services.swarm_manager import SwarmManagerError, get_manager_overview, get_worker_join_token
from app.services.wireguard_server import WireGuardServerError, apply_server_peer

router = APIRouter(prefix="/platform")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_node(node: Node) -> NodeResponse:
    return NodeResponse(
        id=node.id,
        seller_user_id=node.seller_user_id,
        node_key=node.node_key,
        device_fingerprint=node.device_fingerprint,
        hostname=node.hostname,
        system=node.system,
        machine=node.machine,
        status=node.status,
        shared_percent_preference=node.shared_percent_preference,
        node_class=node.node_class,
        capabilities=node.capabilities,
        seller_intent=node.seller_intent,
        docker_status=node.docker_status,
        swarm_state=node.swarm_state,
        ready_for_registry_push=bool(node.docker_status),
        needs_docker_setup=not bool(node.docker_status),
        needs_wireguard_setup=True,
        needs_codex_setup=True,
        needs_node_token=False,
        last_heartbeat_at=node.last_heartbeat_at,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def _serialize_image(image: ImageArtifact) -> ImageArtifactResponse:
    return ImageArtifactResponse(
        id=image.id,
        seller_user_id=image.seller_user_id,
        node_id=image.node_id,
        repository=image.repository,
        tag=image.tag,
        digest=image.digest,
        registry=image.registry,
        source_image=image.source_image,
        status=image.status,
        push_ready=image.status == "uploaded",
        created_at=image.created_at,
        updated_at=image.updated_at,
    )


def _serialize_node_token(node_token: NodeRegistrationToken) -> NodeTokenListResponse:
    return NodeTokenListResponse(
        id=node_token.id,
        label=node_token.label,
        expires_at=node_token.expires_at,
        revoked=node_token.revoked,
        used_node_key=node_token.used_node_key,
        last_used_at=node_token.last_used_at,
        created_at=node_token.created_at,
    )


def _serialize_activity(event: ActivityEvent) -> ActivityEventResponse:
    return ActivityEventResponse(
        id=event.id,
        seller_user_id=event.seller_user_id,
        node_id=event.node_id,
        image_id=event.image_id,
        event_type=event.event_type,
        summary=event.summary,
        detail=event.detail,
        event_metadata=event.event_metadata,
        created_at=event.created_at,
    )


def _get_node_for_token(db: Session, node_token: NodeRegistrationToken, node_key: str) -> Node | None:
    statement = select(Node).where(Node.node_key == node_key, Node.seller_user_id == node_token.user_id)
    return db.scalar(statement)


@router.post("/node-registration-token", response_model=NodeTokenResponse)
def create_node_registration_token(
    payload: IssueNodeTokenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NodeTokenResponse:
    token = issue_node_registration_token(db, current_user, payload.label, payload.expires_hours)
    log_activity(
        db,
        seller_user_id=current_user.id,
        event_type="node_token_issued",
        summary="Issued node registration token",
        detail=payload.label,
        metadata={"label": payload.label, "expires_hours": payload.expires_hours},
    )
    db.commit()
    return NodeTokenResponse(
        node_registration_token=token.token,
        expires_at=token.expires_at,
        label=token.label,
    )


@router.post("/nodes/register", response_model=NodeResponse)
def register_node(
    payload: NodeRegisterRequest,
    node_token: NodeRegistrationToken = Depends(get_current_node_token),
    db: Session = Depends(get_db),
) -> NodeResponse:
    if node_token.used_node_key and node_token.used_node_key != payload.node_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node registration token is already bound to another node.",
        )

    node = _get_node_for_token(db, node_token, payload.node_id)
    if node is None:
        node = Node(
            seller_user_id=node_token.user_id,
            node_key=payload.node_id,
            device_fingerprint=payload.device_fingerprint,
            hostname=payload.hostname,
            system=payload.system,
            machine=payload.machine,
            status="available",
            shared_percent_preference=payload.shared_percent_preference,
            node_class=payload.node_class,
            capabilities=payload.capabilities,
            seller_intent=payload.seller_intent,
            docker_status=payload.docker_status,
            swarm_state=payload.swarm_state,
            last_heartbeat_at=utcnow(),
        )
        db.add(node)
    else:
        node.device_fingerprint = payload.device_fingerprint
        node.hostname = payload.hostname
        node.system = payload.system
        node.machine = payload.machine
        node.shared_percent_preference = payload.shared_percent_preference
        node.node_class = payload.node_class
        node.capabilities = payload.capabilities
        node.seller_intent = payload.seller_intent
        node.docker_status = payload.docker_status
        node.swarm_state = payload.swarm_state
        node.status = "available"
        node.last_heartbeat_at = utcnow()

    node_token.used_node_key = payload.node_id
    node_token.last_used_at = utcnow()
    log_activity(
        db,
        seller_user_id=node_token.user_id,
        node_id=node.id,
        event_type="node_registered",
        summary=f"Registered node {payload.hostname}",
        detail=payload.seller_intent,
        metadata={"node_key": payload.node_id, "node_class": payload.node_class},
    )
    db.commit()
    db.refresh(node)
    return _serialize_node(node)


@router.post("/nodes/heartbeat", response_model=NodeResponse)
def heartbeat_node(
    payload: NodeHeartbeatRequest,
    node_token: NodeRegistrationToken = Depends(get_current_node_token),
    db: Session = Depends(get_db),
) -> NodeResponse:
    node = _get_node_for_token(db, node_token, payload.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node is not registered.")

    node.status = payload.status
    node.docker_status = payload.docker_status
    node.swarm_state = payload.swarm_state
    if payload.capabilities is not None:
        node.capabilities = payload.capabilities
    node.last_heartbeat_at = utcnow()
    node_token.last_used_at = utcnow()
    log_activity(
        db,
        seller_user_id=node_token.user_id,
        node_id=node.id,
        event_type="node_heartbeat",
        summary=f"Heartbeat from {node.hostname}",
        metadata={"status": payload.status},
    )
    db.commit()
    db.refresh(node)
    return _serialize_node(node)


@router.get("/nodes", response_model=list[NodeResponse])
def list_seller_nodes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NodeResponse]:
    nodes = db.scalars(select(Node).where(Node.seller_user_id == current_user.id).order_by(Node.id)).all()
    return [_serialize_node(node) for node in nodes]


@router.get("/nodes/{node_id}", response_model=NodeResponse)
def get_seller_node(
    node_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NodeResponse:
    node = db.scalar(select(Node).where(Node.id == node_id, Node.seller_user_id == current_user.id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    return _serialize_node(node)


@router.post("/images/report", response_model=ImageArtifactResponse)
def report_uploaded_image(
    payload: ImageReportRequest,
    node_token: NodeRegistrationToken = Depends(get_current_node_token),
    db: Session = Depends(get_db),
) -> ImageArtifactResponse:
    node = _get_node_for_token(db, node_token, payload.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node is not registered.")

    statement = select(ImageArtifact).where(
        ImageArtifact.seller_user_id == node_token.user_id,
        ImageArtifact.repository == payload.repository,
        ImageArtifact.tag == payload.tag,
        ImageArtifact.registry == payload.registry,
    )
    image = db.scalar(statement)
    if image is None:
        image = ImageArtifact(
            seller_user_id=node_token.user_id,
            node_id=node.id,
            repository=payload.repository,
            tag=payload.tag,
            digest=payload.digest,
            registry=payload.registry,
            source_image=payload.source_image,
            status=payload.status,
        )
        db.add(image)
    else:
        image.node_id = node.id
        image.digest = payload.digest
        image.source_image = payload.source_image
        image.status = payload.status

    node_token.last_used_at = utcnow()
    db.flush()
    log_activity(
        db,
        seller_user_id=node_token.user_id,
        node_id=node.id,
        image_id=image.id,
        event_type="image_reported",
        summary=f"Reported image {payload.repository}:{payload.tag}",
        metadata={"repository": payload.repository, "tag": payload.tag, "registry": payload.registry},
    )
    db.commit()
    db.refresh(image)

    try:
        run_offer_probe_and_pricing(
            db,
            seller_user_id=node_token.user_id,
            image=image,
            node=node,
            timeout_seconds=settings.PRICING_PROBE_TIMEOUT_SECONDS,
        )
    except SwarmManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Image reported, but auto-publish failed during remote probe: {exc}",
        ) from exc
    except PricingEngineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Image reported, but auto-publish failed during pricing: {exc}",
        ) from exc

    return _serialize_image(image)


@router.get("/images", response_model=list[ImageArtifactResponse])
def list_seller_images(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ImageArtifactResponse]:
    images = db.scalars(
        select(ImageArtifact).where(ImageArtifact.seller_user_id == current_user.id).order_by(ImageArtifact.id)
    ).all()
    return [_serialize_image(image) for image in images]


@router.get("/images/{image_id}", response_model=ImageArtifactResponse)
def get_seller_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageArtifactResponse:
    image = db.scalar(
        select(ImageArtifact).where(ImageArtifact.id == image_id, ImageArtifact.seller_user_id == current_user.id)
    )
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return _serialize_image(image)


@router.get("/node-registration-tokens", response_model=list[NodeTokenListResponse])
def list_node_registration_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NodeTokenListResponse]:
    tokens = db.scalars(
        select(NodeRegistrationToken)
        .where(NodeRegistrationToken.user_id == current_user.id)
        .order_by(NodeRegistrationToken.id.desc())
    ).all()
    return [_serialize_node_token(token) for token in tokens]


@router.get("/activity", response_model=list[ActivityEventResponse])
def list_platform_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActivityEventResponse]:
    events = db.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.seller_user_id == current_user.id)
        .order_by(ActivityEvent.id.desc())
        .limit(100)
    ).all()
    return [_serialize_activity(event) for event in events]


@router.get("/overview", response_model=PlatformOverviewResponse)
def seller_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlatformOverviewResponse:
    nodes = db.scalars(select(Node).where(Node.seller_user_id == current_user.id).order_by(Node.id)).all()
    images = db.scalars(
        select(ImageArtifact).where(ImageArtifact.seller_user_id == current_user.id).order_by(ImageArtifact.id)
    ).all()
    return PlatformOverviewResponse(
        seller_id=current_user.id,
        node_count=len(nodes),
        image_count=len(images),
        nodes=[_serialize_node(node) for node in nodes],
        images=[_serialize_image(image) for image in images],
    )


@router.get("/runtime/codex", response_model=CodexRuntimeBootstrapResponse)
def get_codex_runtime_bootstrap(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CodexRuntimeBootstrapResponse:
    try:
        bootstrap = build_codex_runtime_bootstrap(settings)
    except RuntimeBootstrapError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    log_activity(
        db,
        seller_user_id=current_user.id,
        event_type="codex_runtime_issued",
        summary="Issued CodeX runtime bootstrap",
        metadata={"auth_source": bootstrap["auth_source"], "model": bootstrap["model"]},
    )
    db.commit()
    return CodexRuntimeBootstrapResponse(**bootstrap)


@router.post("/nodes/wireguard/bootstrap", response_model=WireGuardBootstrapResponse)
def create_wireguard_bootstrap(
    payload: WireGuardBootstrapRequest,
    node_token: NodeRegistrationToken = Depends(get_current_node_token),
    db: Session = Depends(get_db),
) -> WireGuardBootstrapResponse:
    node = _get_node_for_token(db, node_token, payload.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node is not registered.")

    try:
        bootstrap = build_wireguard_bootstrap(settings, node, payload.client_public_key)
    except RuntimeBootstrapError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if settings.WIREGUARD_SERVER_SSH_ENABLED:
        try:
            apply_result = apply_server_peer(
                settings,
                public_key=payload.client_public_key,
                client_address=bootstrap["client_address"],
                persistent_keepalive=bootstrap["persistent_keepalive"],
            )
        except WireGuardServerError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        bootstrap["server_peer_apply_required"] = False
        bootstrap["server_peer_apply_status"] = "applied"
        bootstrap["server_peer_apply_error"] = None
        bootstrap["activation_mode"] = "server_peer_applied"
    else:
        apply_result = None
        bootstrap["server_peer_apply_status"] = "pending_manual_apply"
        bootstrap["server_peer_apply_error"] = None

    node_token.last_used_at = utcnow()
    log_activity(
        db,
        seller_user_id=node_token.user_id,
        node_id=node.id,
        event_type="wireguard_profile_issued",
        summary=f"Issued WireGuard profile for {node.hostname}",
        metadata={
            "node_key": node.node_key,
            "client_public_key": payload.client_public_key,
            "client_address": bootstrap["client_address"],
            "server_peer_apply_status": bootstrap["server_peer_apply_status"],
            "server_peer_applied": not bootstrap["server_peer_apply_required"],
            "server_peer_apply_runtime_ok": apply_result["ok"] if apply_result is not None else False,
        },
    )
    db.commit()
    return WireGuardBootstrapResponse(**bootstrap)


@router.get("/swarm/worker-join-token", response_model=SwarmWorkerJoinTokenResponse)
def read_swarm_worker_join_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SwarmWorkerJoinTokenResponse:
    try:
        payload = get_worker_join_token(settings)
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    log_activity(
        db,
        seller_user_id=current_user.id,
        event_type="swarm_worker_join_token_issued",
        summary="Issued swarm worker join token",
        metadata={"manager_host": payload["manager_host"], "manager_port": payload["manager_port"]},
    )
    db.commit()
    return SwarmWorkerJoinTokenResponse(**payload)


@router.get("/swarm/overview", response_model=SwarmRemoteOverviewResponse)
def read_remote_swarm_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SwarmRemoteOverviewResponse:
    try:
        payload = get_manager_overview(settings)
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    log_activity(
        db,
        seller_user_id=current_user.id,
        event_type="swarm_overview_viewed",
        summary="Viewed remote swarm overview",
        metadata={"manager_host": payload["manager_host"], "manager_port": payload["manager_port"]},
    )
    db.commit()
    return SwarmRemoteOverviewResponse(**payload)
