from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    error_code: str
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = None
