from fastapi import APIRouter, Depends, HTTPException, status

from backend_app.api.deps import get_node_service
from backend_app.core.config import get_settings
from backend_app.schemas.health import AdapterHealthRead, HealthRead, ReadyRead
from backend_app.services.node_service import NodeService

router = APIRouter(tags=["health"])
settings = get_settings()


def _read_adapter_health(service: NodeService) -> AdapterHealthRead:
    try:
        return service.get_adapter_health()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Adapter unavailable",
        ) from exc


@router.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    return HealthRead(service=settings.project_name)


@router.get("/ready", response_model=ReadyRead)
def ready(service: NodeService = Depends(get_node_service)) -> ReadyRead:
    return ReadyRead(status="ready", adapter=_read_adapter_health(service))


@router.get("/adapter/health", response_model=AdapterHealthRead)
def adapter_health(service: NodeService = Depends(get_node_service)) -> AdapterHealthRead:
    return _read_adapter_health(service)
