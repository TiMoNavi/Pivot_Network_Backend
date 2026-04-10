from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_adapter_auth
from app.dependencies import get_wireguard_service
from app.schemas.wireguard import WireGuardPeerApplyRequest, WireGuardPeerRemoveRequest, WireGuardPeerResponse
from app.services.wireguard import WireGuardService

router = APIRouter(
    prefix="/wireguard",
    tags=["wireguard"],
    dependencies=[Depends(require_adapter_auth)],
)


@router.post("/peers/apply", response_model=WireGuardPeerResponse)
def apply_peer(
    request: WireGuardPeerApplyRequest,
    service: WireGuardService = Depends(get_wireguard_service),
):
    return service.apply_peer(request)


@router.post("/peers/remove", response_model=WireGuardPeerResponse)
def remove_peer(
    request: WireGuardPeerRemoveRequest,
    service: WireGuardService = Depends(get_wireguard_service),
):
    return service.remove_peer(request)
