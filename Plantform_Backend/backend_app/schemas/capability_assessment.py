from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CapabilityAssessmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    onboarding_session_id: str | None = Field(default=None, min_length=1, max_length=64)
    compute_node_id: str | None = Field(default=None, min_length=1, max_length=128)
    node_ref: str | None = Field(default=None, min_length=1, max_length=128)
    requested_offer_tier: str | None = Field(default=None, min_length=1, max_length=32)
    requested_accelerator: str | None = Field(default=None, min_length=1, max_length=32)
    seller_reported_capabilities: dict[str, Any] = Field(default_factory=dict)
    seller_reported_benchmarks: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self) -> "CapabilityAssessmentCreateRequest":
        if self.onboarding_session_id is None and self.compute_node_id is None:
            raise ValueError("capability assessment requires onboarding_session_id or compute_node_id.")
        return self


class CapabilityAssessmentResolvedTargetRead(BaseModel):
    onboarding_session_id: str | None = None
    seller_user_id: str
    compute_node_id: str | None = None
    node_ref: str | None = None


class CapabilityAssessmentRead(BaseModel):
    assessment_id: str
    assessment_status: str
    resolved_target: CapabilityAssessmentResolvedTargetRead
    sources_used: dict[str, Any] = Field(default_factory=dict)
    measured_capabilities: dict[str, Any] = Field(default_factory=dict)
    pricing_decision: dict[str, Any] = Field(default_factory=dict)
    runtime_image_validation: dict[str, Any] = Field(default_factory=dict)
    recommended_offer: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
