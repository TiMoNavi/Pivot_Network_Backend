from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from backend_app.api.deps import get_adapter_client, get_current_user
from backend_app.clients.adapter.client import AdapterClient, AdapterClientError

router = APIRouter(prefix="/adapter-proxy", tags=["adapter-proxy"])


def _handle(exc: AdapterClientError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.payload or {"detail": exc.detail})


@router.get("/swarm/overview")
def proxy_swarm_overview(
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.get_swarm_overview()
    except AdapterClientError as exc:
        raise _handle(exc)


@router.get("/swarm/nodes")
def proxy_swarm_nodes(
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.list_nodes()
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/nodes/inspect")
def proxy_swarm_nodes_inspect(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.inspect_node(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/nodes/join-material")
def proxy_swarm_nodes_join_material(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.get_join_material(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/nodes/claim")
def proxy_swarm_nodes_claim(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.claim_node(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/nodes/availability")
def proxy_swarm_nodes_availability(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.set_node_availability(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/nodes/remove")
def proxy_swarm_nodes_remove(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.remove_node(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/runtime-images/validate")
def proxy_runtime_images_validate(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.validate_runtime_image(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/nodes/probe")
def proxy_nodes_probe(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.probe_node(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/services/inspect")
def proxy_services_inspect(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.inspect_service(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/runtime-session-bundles/create")
def proxy_runtime_bundles_create(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.create_runtime_bundle(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/runtime-session-bundles/inspect")
def proxy_runtime_bundles_inspect(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.inspect_runtime_bundle(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/swarm/runtime-session-bundles/remove")
def proxy_runtime_bundles_remove(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.remove_runtime_bundle(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/wireguard/peers/apply")
def proxy_wireguard_apply(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.apply_wireguard_peer(payload)
    except AdapterClientError as exc:
        raise _handle(exc)


@router.post("/wireguard/peers/remove")
def proxy_wireguard_remove(
    payload: dict[str, Any] = Body(default_factory=dict),
    _user=Depends(get_current_user),
    client: AdapterClient = Depends(get_adapter_client),
) -> dict[str, Any]:
    try:
        return client.remove_wireguard_peer(payload)
    except AdapterClientError as exc:
        raise _handle(exc)
