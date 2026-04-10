from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AdapterHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, error_code: str | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code or detail


class NotImplementedYetError(Exception):
    def __init__(self, detail: str = "not_implemented_yet") -> None:
        self.detail = detail
        self.error_code = "not_implemented_yet"
        super().__init__(detail)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _payload(request: Request, detail: str, error_code: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "detail": detail,
        "error_code": error_code,
        "request_id": _request_id(request),
    }
    payload.update(extra)
    return payload


async def adapter_http_exception_handler(request: Request, exc: AdapterHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(request, str(exc.detail), exc.error_code),
    )


async def not_implemented_handler(request: Request, exc: NotImplementedYetError) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=_payload(request, exc.detail, exc.error_code),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_payload(
            request,
            "validation_error",
            "validation_error",
            errors=exc.errors(),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled adapter exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=_payload(request, "internal_error", "internal_error"),
    )
