from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_adapter_auth
from app.dependencies import get_swarm_node_service
from app.schemas.swarm import (
    AvailabilityRequest,
    AvailabilityResponse,
    ClaimRequest,
    ClaimResponse,
    JoinMaterialRequest,
    JoinMaterialResponse,
    NodeInspectRequest,
    NodeInspectResponse,
    NodeSearchResponse,
    RemoveRequest,
    RemoveResponse,
    SwarmNodesResponse,
    SwarmOverviewResponse,
)
from app.services.swarm_nodes import SwarmNodeService

router = APIRouter(
    prefix="/swarm",
    tags=["swarm-nodes"],
    dependencies=[Depends(require_adapter_auth)],
)


@router.get("/overview", response_model=SwarmOverviewResponse)
def get_overview(service: SwarmNodeService = Depends(get_swarm_node_service)) -> SwarmOverviewResponse:
    return service.get_overview()


@router.get("/nodes", response_model=SwarmNodesResponse)
def list_nodes(service: SwarmNodeService = Depends(get_swarm_node_service)) -> SwarmNodesResponse:
    return service.list_nodes()


@router.post("/nodes/inspect", response_model=NodeInspectResponse)
def inspect_node(
    request: NodeInspectRequest,
    service: SwarmNodeService = Depends(get_swarm_node_service),
) -> NodeInspectResponse:
    return service.inspect_node(request)


@router.get("/nodes/by-ref/{node_ref}", response_model=NodeInspectResponse)
def inspect_node_by_ref(
    node_ref: str,
    service: SwarmNodeService = Depends(get_swarm_node_service),
) -> NodeInspectResponse:
    return service.inspect_node(NodeInspectRequest(node_ref=node_ref))


@router.get("/nodes/by-compute-node-id/{compute_node_id}", response_model=NodeInspectResponse)
def inspect_node_by_compute_node_id(
    compute_node_id: str,
    service: SwarmNodeService = Depends(get_swarm_node_service),
) -> NodeInspectResponse:
    return service.inspect_node_by_compute_node_id(compute_node_id)


@router.get("/nodes/search", response_model=NodeSearchResponse)
def search_nodes(
    query: str | None = None,
    seller_user_id: str | None = None,
    compute_node_id: str | None = None,
    role: str | None = None,
    status: str | None = None,
    availability: str | None = None,
    accelerator: str | None = None,
    compute_enabled: bool | None = None,
    service: SwarmNodeService = Depends(get_swarm_node_service),
) -> NodeSearchResponse:
    return service.search_nodes(
        query=query,
        seller_user_id=seller_user_id,
        compute_node_id=compute_node_id,
        role=role,
        status=status,
        availability=availability,
        accelerator=accelerator,
        compute_enabled=compute_enabled,
    )


@router.post("/nodes/join-material", response_model=JoinMaterialResponse)
def join_material(
    request: JoinMaterialRequest,
    service: SwarmNodeService = Depends(get_swarm_node_service),
) -> JoinMaterialResponse:
    return service.get_join_material(request)


@router.post("/nodes/claim", response_model=ClaimResponse)
def claim_node(
    request: ClaimRequest,
    service: SwarmNodeService = Depends(get_swarm_node_service),
) -> ClaimResponse:
    return service.claim_node(request)


@router.post("/nodes/availability", response_model=AvailabilityResponse)
def set_availability(
    request: AvailabilityRequest,
    service: SwarmNodeService = Depends(get_swarm_node_service),
) -> AvailabilityResponse:
    return service.set_availability(request)


@router.post("/nodes/remove", response_model=RemoveResponse)
def remove_node(
    request: RemoveRequest,
    service: SwarmNodeService = Depends(get_swarm_node_service),
) -> RemoveResponse:
    return service.remove_node(request)
