from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "backend"


class ReadinessResponse(HealthResponse):
    database: str

