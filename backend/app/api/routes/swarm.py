from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import swarm_adapter

router = APIRouter(prefix="/swarm")


@router.get("/health")
def read_swarm_health() -> JSONResponse:
    try:
        payload = swarm_adapter.get_swarm_health()
    except swarm_adapter.SwarmAdapterUnavailableError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "adapter": "docker-cli",
                "reachable": False,
                "detail": str(exc),
            },
        )

    return JSONResponse(status_code=200, content=payload)
