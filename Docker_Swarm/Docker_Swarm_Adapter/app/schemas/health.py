from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    adapter: str
    docker_cli: bool
    swarm_state: str
    wireguard_readable: bool
