from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ActivityEventResponse(BaseModel):
    id: int
    seller_user_id: int | None
    node_id: int | None
    image_id: int | None
    event_type: str
    summary: str
    detail: str | None
    event_metadata: dict[str, Any]
    created_at: datetime
