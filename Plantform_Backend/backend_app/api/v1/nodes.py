from fastapi import APIRouter, Depends, Query

from backend_app.api.deps import get_node_service
from backend_app.schemas.nodes import NodeDetailRead, NodeListRead, NodePollSnapshotRead, SwarmOverviewRead
from backend_app.services.node_service import NodeService

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/swarm/overview", response_model=SwarmOverviewRead)
def swarm_overview(service: NodeService = Depends(get_node_service)) -> SwarmOverviewRead:
    return service.get_overview()


@router.get("/nodes", response_model=NodeListRead)
def list_nodes(
    query: str | None = None,
    seller_user_id: str | None = None,
    compute_node_id: str | None = None,
    role: str | None = None,
    status: str | None = None,
    availability: str | None = None,
    accelerator: str | None = None,
    compute_enabled: bool | None = None,
    service: NodeService = Depends(get_node_service),
) -> NodeListRead:
    return service.list_nodes(
        query=query,
        seller_user_id=seller_user_id,
        compute_node_id=compute_node_id,
        role=role,
        status=status,
        availability=availability,
        accelerator=accelerator,
        compute_enabled=compute_enabled,
    )


@router.get("/nodes/search", response_model=NodeListRead)
def search_nodes(
    query: str | None = Query(default=None),
    seller_user_id: str | None = Query(default=None),
    compute_node_id: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
    availability: str | None = Query(default=None),
    accelerator: str | None = Query(default=None),
    compute_enabled: bool | None = Query(default=None),
    service: NodeService = Depends(get_node_service),
) -> NodeListRead:
    return service.list_nodes(
        query=query,
        seller_user_id=seller_user_id,
        compute_node_id=compute_node_id,
        role=role,
        status=status,
        availability=availability,
        accelerator=accelerator,
        compute_enabled=compute_enabled,
    )


@router.get("/nodes/by-compute-node-id/{compute_node_id}", response_model=NodeDetailRead)
def node_detail_by_compute_node_id(
    compute_node_id: str,
    service: NodeService = Depends(get_node_service),
) -> NodeDetailRead:
    return service.get_node_detail_by_compute_node_id(compute_node_id)


@router.get("/nodes/{node_ref}", response_model=NodeDetailRead)
def node_detail(node_ref: str, service: NodeService = Depends(get_node_service)) -> NodeDetailRead:
    return service.get_node_detail(node_ref)


@router.get("/swarm/poll-snapshot", response_model=NodePollSnapshotRead)
def poll_snapshot(
    query: str | None = None,
    seller_user_id: str | None = None,
    compute_node_id: str | None = None,
    role: str | None = None,
    status: str | None = None,
    availability: str | None = None,
    accelerator: str | None = None,
    compute_enabled: bool | None = None,
    service: NodeService = Depends(get_node_service),
) -> NodePollSnapshotRead:
    return service.poll_snapshot(
        query=query,
        seller_user_id=seller_user_id,
        compute_node_id=compute_node_id,
        role=role,
        status=status,
        availability=availability,
        accelerator=accelerator,
        compute_enabled=compute_enabled,
    )
