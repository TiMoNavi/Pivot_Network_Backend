from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_adapter_auth
from app.dependencies import get_runtime_service
from app.schemas.runtime import (
    NodeProbeRequest,
    NodeProbeResponse,
    RuntimeBundleResponse,
    RuntimeImageValidateRequest,
    RuntimeImageValidateResponse,
    RuntimeSessionBundleCreateRequest,
    RuntimeSessionBundleInspectRequest,
    RuntimeSessionBundleRemoveRequest,
    ServiceInspectRequest,
    ServiceInspectResponse,
)
from app.services.swarm_runtime import SwarmRuntimeService

router = APIRouter(
    prefix="/swarm",
    tags=["swarm-runtime"],
    dependencies=[Depends(require_adapter_auth)],
)


@router.post("/runtime-images/validate", response_model=RuntimeImageValidateResponse)
def validate_runtime_image(
    request: RuntimeImageValidateRequest,
    service: SwarmRuntimeService = Depends(get_runtime_service),
):
    return service.validate_runtime_image(request)


@router.post("/nodes/probe", response_model=NodeProbeResponse)
def probe_node(
    request: NodeProbeRequest,
    service: SwarmRuntimeService = Depends(get_runtime_service),
):
    return service.probe_node(request)


@router.post("/services/inspect", response_model=ServiceInspectResponse)
def inspect_service(
    request: ServiceInspectRequest,
    service: SwarmRuntimeService = Depends(get_runtime_service),
):
    return service.inspect_service(request)


@router.post("/runtime-session-bundles/create", response_model=RuntimeBundleResponse)
def create_runtime_bundle(
    request: RuntimeSessionBundleCreateRequest,
    service: SwarmRuntimeService = Depends(get_runtime_service),
):
    return service.create_runtime_bundle(request)


@router.post("/runtime-session-bundles/inspect", response_model=RuntimeBundleResponse)
def inspect_runtime_bundle(
    request: RuntimeSessionBundleInspectRequest,
    service: SwarmRuntimeService = Depends(get_runtime_service),
):
    return service.inspect_runtime_bundle(request)


@router.post("/runtime-session-bundles/remove", response_model=RuntimeBundleResponse)
def remove_runtime_bundle(
    request: RuntimeSessionBundleRemoveRequest,
    service: SwarmRuntimeService = Depends(get_runtime_service),
):
    return service.remove_runtime_bundle(request)
