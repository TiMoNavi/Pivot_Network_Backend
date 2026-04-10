from __future__ import annotations

from typing import Any


class LocalAppError(Exception):
    def __init__(
        self,
        *,
        step: str,
        code: str,
        message: str,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.step = step
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "step": self.step,
                "code": self.code,
                "message": self.message,
                "hint": self.hint,
                "details": self.details,
            }
        }
