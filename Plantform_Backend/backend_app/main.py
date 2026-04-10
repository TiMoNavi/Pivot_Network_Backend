from fastapi import FastAPI

from backend_app.api.router import api_router
from backend_app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.project_name,
    version=settings.project_version,
    debug=settings.debug,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "message": "Plantform Backend is running.",
        "docs": "/docs",
    }

