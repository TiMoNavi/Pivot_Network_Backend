from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def read_health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
    }
