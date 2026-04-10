from pydantic import BaseModel


class HealthRead(BaseModel):
    status: str = "ok"
    service: str


class AdapterHealthRead(BaseModel):
    status: str
    adapter_name: str | None = None
    swarm_manager_addr: str | None = None
    wireguard_interface: str | None = None
    portainer_url: str | None = None


class ReadyRead(BaseModel):
    status: str
    adapter: AdapterHealthRead
