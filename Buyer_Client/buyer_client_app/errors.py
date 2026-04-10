from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LocalAppError(Exception):
    step: str
    code: str
    message: str
    hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    status_code: int = 400

    def __str__(self) -> str:
        return self.message

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
