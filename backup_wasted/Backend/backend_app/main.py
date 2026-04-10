import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend_app.api.router import api_router
from backend_app.core.config import get_settings
from backend_app.workers.runner import run_builtin_workers, shutdown_worker_task

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker_task: asyncio.Task[None] | None = None
    stop_event = asyncio.Event()
    if settings.enable_builtin_workers:
        worker_task = asyncio.create_task(run_builtin_workers(stop_event))
    try:
        yield
    finally:
        if worker_task is not None:
            await shutdown_worker_task(worker_task, stop_event)


app = FastAPI(
    title=settings.project_name,
    version=settings.project_version,
    debug=settings.debug,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    lifespan=lifespan,
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "message": "Pivot Platform Backend is running.",
        "docs": "/docs",
    }
