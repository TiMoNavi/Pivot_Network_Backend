from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request

from app.config import get_settings
from app.errors import (
    AdapterHTTPException,
    NotImplementedYetError,
    adapter_http_exception_handler,
    not_implemented_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.routers.health import router as health_router
from app.routers.swarm_nodes import router as swarm_nodes_router
from app.routers.swarm_runtime import router as swarm_runtime_router
from app.routers.wireguard import router as wireguard_router


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


configure_logging()
settings = get_settings()

app = FastAPI(title="Docker Swarm Adapter", version="0.1.0")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_exception_handler(AdapterHTTPException, adapter_http_exception_handler)
app.add_exception_handler(NotImplementedYetError, not_implemented_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

from fastapi.exceptions import RequestValidationError  # noqa: E402

app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(health_router)
app.include_router(swarm_nodes_router)
app.include_router(swarm_runtime_router)
app.include_router(wireguard_router)
