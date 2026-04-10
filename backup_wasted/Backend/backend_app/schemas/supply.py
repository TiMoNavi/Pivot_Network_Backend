from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SellerImageReportRequest(BaseModel):
    node_ref: str
    runtime_image_ref: str
    repository: str
    tag: str
    registry: str
    digest: str | None = None


class ImageArtifactRead(BaseModel):
    id: str
    seller_user_id: str
    swarm_node_id: str
    repository: str
    tag: str
    digest: str | None = None
    registry: str
    base_image_ref: str | None = None
    runtime_contract_version: str | None = None
    status: str
    created_at: datetime


class ImageOfferRead(BaseModel):
    id: str
    seller_user_id: str
    swarm_node_id: str
    image_artifact_id: str
    runtime_image_ref: str
    offer_status: str
    validation_status: str | None = None
    validation_payload: dict[str, Any] | None = None
    validation_error: str | None = None
    shell_agent_status: str | None = None
    probe_status: str | None = None
    probe_measured_capabilities: dict[str, Any] | None = None
    last_validated_at: datetime | None = None
    last_probed_at: datetime | None = None


class SellerImageReportResponse(BaseModel):
    artifact: ImageArtifactRead
    offer: ImageOfferRead
    validate_result: dict[str, Any]
    probe_result: dict[str, Any]
