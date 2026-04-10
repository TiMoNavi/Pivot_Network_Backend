from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend_app.clients.adapter_client import AdapterClient, AdapterClientError
from backend_app.core.security import new_object_id
from backend_app.repositories.seller_onboarding_repository import SellerOnboardingRepository
from backend_app.repositories.trade_repository import TradeRepository
from backend_app.schemas.capability_assessment import (
    CapabilityAssessmentCreateRequest,
    CapabilityAssessmentRead,
    CapabilityAssessmentResolvedTargetRead,
)
from backend_app.services.offer_commercialization_service import OfferCommercializationService
from backend_app.storage.memory_store import JoinSessionRecord, SellerCapabilityAssessmentRecord


LANE_RULES: dict[str, dict[str, Any]] = {
    "gpu": {
        "default_tier": "medium",
        "offer_profile_id": "profile-medium-gpu",
        "runtime_image_ref": "registry.example.com/pivot/runtime:python-gpu-v1",
        "price_snapshot": {"currency": "CNY", "hourly_price": 12.5},
        "title": "Medium GPU Runtime",
    },
    "cpu": {
        "default_tier": "small",
        "offer_profile_id": "profile-small-cpu",
        "runtime_image_ref": "registry.example.com/pivot/runtime:python-cpu-v1",
        "price_snapshot": {"currency": "CNY", "hourly_price": 4.0},
        "title": "Small CPU Runtime",
    },
}

SUPPORTED_TIERS: dict[str, set[str]] = {
    "gpu": {"medium"},
    "cpu": {"small"},
}


class CapabilityAssessmentService:
    def __init__(
        self,
        seller_onboarding_repository: SellerOnboardingRepository,
        trade_repository: TradeRepository,
        adapter_client: AdapterClient,
        offer_commercialization_service: OfferCommercializationService,
    ) -> None:
        self.seller_onboarding_repository = seller_onboarding_repository
        self.trade_repository = trade_repository
        self.adapter_client = adapter_client
        self.offer_commercialization_service = offer_commercialization_service

    def create_assessment(
        self,
        actor_user_id: str,
        actor_role: str,
        payload: CapabilityAssessmentCreateRequest,
    ) -> CapabilityAssessmentRead:
        session = self._resolve_session(actor_user_id, actor_role, payload)
        return self._run_assessment(session=session, payload=payload, apply_offer=False)

    def assess_verified_session(self, session_id: str, seller_user_id: str) -> CapabilityAssessmentRead:
        session = self.seller_onboarding_repository.get_session(session_id)
        if session is None or session.seller_user_id != seller_user_id:
            raise ValueError("Onboarding session not found.")
        payload = CapabilityAssessmentCreateRequest(onboarding_session_id=session_id)
        return self._run_assessment(session=session, payload=payload, apply_offer=True)

    def _resolve_session(
        self,
        actor_user_id: str,
        actor_role: str,
        payload: CapabilityAssessmentCreateRequest,
    ) -> JoinSessionRecord:
        if payload.onboarding_session_id is not None:
            session = self.seller_onboarding_repository.get_session(payload.onboarding_session_id)
            if session is None:
                raise ValueError("Onboarding session not found.")
            if actor_role != "platform_admin" and session.seller_user_id != actor_user_id:
                raise ValueError("Onboarding session not found.")
            return session

        compute_node_id = str(payload.compute_node_id or "").strip()
        if not compute_node_id:
            raise ValueError("Onboarding session not found.")

        if actor_role == "platform_admin":
            sessions = self.seller_onboarding_repository.list_sessions_for_compute_node_id(compute_node_id)
            if not sessions:
                raise ValueError("Onboarding session not found.")
            seller_ids = {item.seller_user_id for item in sessions}
            if len(seller_ids) > 1:
                raise ValueError("Compute node is ambiguous across sellers.")
            verified = [item for item in sessions if item.status == "verified"]
            return verified[0] if verified else sessions[0]

        sessions = self.seller_onboarding_repository.list_sessions_for_compute_node_id(
            compute_node_id,
            seller_user_id=actor_user_id,
        )
        if not sessions:
            raise ValueError("Onboarding session not found.")
        verified = [item for item in sessions if item.status == "verified"]
        return verified[0] if verified else sessions[0]

    def _run_assessment(
        self,
        *,
        session: JoinSessionRecord,
        payload: CapabilityAssessmentCreateRequest,
        apply_offer: bool,
    ) -> CapabilityAssessmentRead:
        now = datetime.now(UTC)
        assessment_id = new_object_id("assessment")
        substrate_probe = self.seller_onboarding_repository.get_linux_substrate_probe(session.id)
        join_complete = self.seller_onboarding_repository.get_join_complete(session.id)
        manager_acceptance = self.seller_onboarding_repository.get_manager_acceptance(session.id)

        node_ref = self._clean_optional_string(payload.node_ref)
        if node_ref is None and join_complete is not None:
            node_ref = self._clean_optional_string(join_complete.node_ref)
        if node_ref is None and manager_acceptance is not None:
            node_ref = self._clean_optional_string(manager_acceptance.node_ref)

        compute_node_id = self._clean_optional_string(payload.compute_node_id) or self._clean_optional_string(
            session.requested_compute_node_id
        )
        if compute_node_id is None and join_complete is not None:
            compute_node_id = self._clean_optional_string(join_complete.compute_node_id)
        if compute_node_id is None and manager_acceptance is not None:
            compute_node_id = self._clean_optional_string(manager_acceptance.compute_node_id)

        warnings: list[str] = []
        request_snapshot = payload.model_dump(mode="python")
        request_snapshot["apply_offer"] = apply_offer

        adapter_probe: dict[str, Any] | None = None
        adapter_probe_error: dict[str, Any] | None = None
        try:
            adapter_probe = self.adapter_client.probe_node(
                {
                    "node_ref": node_ref,
                    "compute_node_id": compute_node_id,
                }
            )
        except AdapterClientError as exc:
            adapter_probe_error = {
                "status_code": exc.status_code,
                "detail": exc.detail,
                "payload": exc.payload,
            }
            warnings.append(exc.detail)

        if adapter_probe is not None:
            node_payload = dict(adapter_probe.get("node") or {})
            node_ref = node_ref or self._clean_optional_string(node_payload.get("node_id"))
            compute_node_id = compute_node_id or self._clean_optional_string(node_payload.get("compute_node_id"))

        measured_capabilities, measured_warnings = self._build_measured_capabilities(
            substrate_probe=substrate_probe,
            adapter_probe=adapter_probe,
            seller_reported_capabilities=payload.seller_reported_capabilities,
        )
        warnings.extend(measured_warnings)

        resolved_accelerator = self._resolve_accelerator(
            requested_accelerator=payload.requested_accelerator,
            session=session,
            substrate_probe=substrate_probe,
            adapter_probe=adapter_probe,
        )
        measured_capabilities["accelerator"] = resolved_accelerator

        resolved_offer_tier, tier_warnings = self._resolve_offer_tier(
            requested_offer_tier=payload.requested_offer_tier,
            session=session,
            accelerator=resolved_accelerator,
        )
        warnings.extend(tier_warnings)

        pricing_decision = self._pricing_decision(resolved_accelerator, resolved_offer_tier)
        runtime_image_ref = str(pricing_decision["runtime_image_ref"])
        probe_status = None if adapter_probe is None else self._clean_optional_string(adapter_probe.get("probe_status"))

        runtime_image_validation: dict[str, Any] = {}
        validation_status: str | None = None
        if adapter_probe is not None and probe_status == "probed":
            try:
                runtime_image_validation = self.adapter_client.validate_runtime_image(
                    {
                        "image_ref": runtime_image_ref,
                        "node_ref": node_ref,
                        "compute_node_id": compute_node_id,
                    }
                )
                validation_status = self._clean_optional_string(runtime_image_validation.get("validation_status"))
            except AdapterClientError as exc:
                runtime_image_validation = {
                    "image_ref": runtime_image_ref,
                    "validation_status": "validation_failed",
                    "detail": exc.detail,
                    "payload": exc.payload,
                }
                validation_status = "validation_failed"
                warnings.append(exc.detail)

        assessment_status = self._assessment_status(
            adapter_probe=adapter_probe,
            adapter_probe_error=adapter_probe_error,
            validation_status=validation_status,
            measured_capabilities=measured_capabilities,
        )

        sources_used = {
            "onboarding_session": {
                "session_id": session.id,
                "session_status": session.status,
                "requested_compute_node_id": session.requested_compute_node_id,
            },
            "onboarding_probe": {
                "linux_substrate_probe_present": substrate_probe is not None,
                "resource_summary": {
                    "cpu_cores": None if substrate_probe is None else substrate_probe.cpu_cores,
                    "memory_gb": None if substrate_probe is None else substrate_probe.memory_gb,
                    "gpu_available": None if substrate_probe is None else substrate_probe.gpu_available,
                },
            },
            "adapter_node_probe": adapter_probe if adapter_probe is not None else {"error": adapter_probe_error},
            "seller_supplemental": {
                "capabilities": dict(payload.seller_reported_capabilities),
                "benchmarks": dict(payload.seller_reported_benchmarks),
            },
        }

        recommended_offer = self._recommended_offer(
            assessment_id=assessment_id,
            assessment_status=assessment_status,
            seller_user_id=session.seller_user_id,
            compute_node_id=compute_node_id,
            pricing_decision=pricing_decision,
            runtime_image_ref=runtime_image_ref,
            measured_capabilities=measured_capabilities,
            session=session,
        )
        recommended_offer["publishable"] = assessment_status == "sellable"
        recommended_offer["inventory_state"]["reason"] = None if assessment_status == "sellable" else assessment_status

        record = SellerCapabilityAssessmentRecord(
            id=assessment_id,
            seller_user_id=session.seller_user_id,
            onboarding_session_id=session.id,
            compute_node_id=compute_node_id,
            node_ref=node_ref,
            assessment_status=assessment_status,
            requested_offer_tier=payload.requested_offer_tier or session.requested_offer_tier,
            requested_accelerator=payload.requested_accelerator or session.requested_accelerator,
            request_snapshot=request_snapshot,
            sources_used=sources_used,
            measured_capabilities=measured_capabilities,
            pricing_decision=pricing_decision,
            runtime_image_validation=runtime_image_validation,
            recommended_offer=recommended_offer,
            warnings=warnings,
            apply_offer=apply_offer,
            apply_result={"status": "not_requested" if not apply_offer else "pending"},
            created_at=now,
            updated_at=now,
        )
        self.trade_repository.save_assessment(record)
        self.trade_repository.commit()

        if apply_offer:
            apply_result = self.offer_commercialization_service.apply_assessment(record)
            record.apply_result = dict(apply_result)
            record.updated_at = datetime.now(UTC)
            self.trade_repository.save_assessment(record)
            self.trade_repository.commit()

        return self._assessment_read(record)

    def _build_measured_capabilities(
        self,
        *,
        substrate_probe: Any | None,
        adapter_probe: dict[str, Any] | None,
        seller_reported_capabilities: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        adapter_capabilities = dict((adapter_probe or {}).get("probe_measured_capabilities") or {})

        cpu_logical = None
        cpu_source = None
        if substrate_probe is not None and substrate_probe.cpu_cores is not None:
            cpu_logical = substrate_probe.cpu_cores
            cpu_source = "onboarding_probe"
        if adapter_capabilities.get("cpu_logical") is not None:
            cpu_logical = int(adapter_capabilities["cpu_logical"])
            cpu_source = "adapter_probe"
        elif cpu_logical is None and seller_reported_capabilities.get("cpu_logical") is not None:
            cpu_logical = int(seller_reported_capabilities["cpu_logical"])
            cpu_source = "seller_supplemental"

        memory_total_mb = None
        memory_source = None
        if substrate_probe is not None and substrate_probe.memory_gb is not None:
            memory_total_mb = int(substrate_probe.memory_gb) * 1024
            memory_source = "onboarding_probe"
        if adapter_capabilities.get("memory_total_mb") is not None:
            memory_total_mb = int(adapter_capabilities["memory_total_mb"])
            memory_source = "adapter_probe"
        elif memory_total_mb is None and seller_reported_capabilities.get("memory_total_mb") is not None:
            memory_total_mb = int(seller_reported_capabilities["memory_total_mb"])
            memory_source = "seller_supplemental"

        gpu_available = None
        gpu_source = None
        if substrate_probe is not None and substrate_probe.gpu_available is not None:
            gpu_available = bool(substrate_probe.gpu_available)
            gpu_source = "onboarding_probe"
        host_probe_gpu = ((adapter_capabilities.get("host_probe") or {}).get("gpu") or {}).get("present")
        if host_probe_gpu is not None:
            gpu_available = bool(host_probe_gpu)
            gpu_source = "adapter_probe"
        elif gpu_available is None and seller_reported_capabilities.get("gpu_available") is not None:
            gpu_available = bool(seller_reported_capabilities["gpu_available"])
            gpu_source = "seller_supplemental"

        generic_resources = adapter_capabilities.get("generic_resources")
        if generic_resources is None:
            generic_resources = seller_reported_capabilities.get("generic_resources") or []

        warnings.extend(list(adapter_probe.get("warnings") or []) if adapter_probe is not None else [])
        if cpu_logical is None:
            warnings.append("cpu_capacity_missing")
        if memory_total_mb is None:
            warnings.append("memory_capacity_missing")

        return (
            {
                "cpu": {"logical": cpu_logical, "source": cpu_source},
                "memory": {"total_mb": memory_total_mb, "source": memory_source},
                "gpu": {"available": gpu_available, "source": gpu_source},
                "generic_resources": generic_resources,
                "warnings": warnings,
            },
            warnings,
        )

    def _resolve_accelerator(
        self,
        *,
        requested_accelerator: str | None,
        session: JoinSessionRecord,
        substrate_probe: Any | None,
        adapter_probe: dict[str, Any] | None,
    ) -> str:
        for candidate in (
            self._clean_optional_string(requested_accelerator),
            self._clean_optional_string(session.requested_accelerator),
        ):
            if candidate in LANE_RULES:
                return candidate

        if substrate_probe is not None and substrate_probe.gpu_available is True:
            return "gpu"
        if substrate_probe is not None and substrate_probe.gpu_available is False:
            return "cpu"

        adapter_accelerator = self._clean_optional_string(
            ((adapter_probe or {}).get("probe_measured_capabilities") or {}).get("accelerator_label")
        )
        if adapter_accelerator in LANE_RULES:
            return adapter_accelerator
        return "cpu"

    def _resolve_offer_tier(
        self,
        *,
        requested_offer_tier: str | None,
        session: JoinSessionRecord,
        accelerator: str,
    ) -> tuple[str, list[str]]:
        warnings: list[str] = []
        lane = LANE_RULES[accelerator]
        default_tier = str(lane["default_tier"])
        for candidate in (
            self._clean_optional_string(requested_offer_tier),
            self._clean_optional_string(session.requested_offer_tier),
        ):
            if candidate is None:
                continue
            if candidate in SUPPORTED_TIERS.get(accelerator, set()):
                return candidate, warnings
            warnings.append("requested_offer_tier_unsupported_fell_back_to_default_lane")
            return default_tier, warnings
        return default_tier, warnings

    def _pricing_decision(self, accelerator: str, offer_tier: str) -> dict[str, Any]:
        lane = dict(LANE_RULES[accelerator])
        return {
            "rule_version": "v1",
            "resolved_accelerator": accelerator,
            "resolved_offer_tier": offer_tier,
            "offer_profile_id": lane["offer_profile_id"],
            "price_snapshot": dict(lane["price_snapshot"]),
            "runtime_image_ref": lane["runtime_image_ref"],
        }

    def _assessment_status(
        self,
        *,
        adapter_probe: dict[str, Any] | None,
        adapter_probe_error: dict[str, Any] | None,
        validation_status: str | None,
        measured_capabilities: dict[str, Any],
    ) -> str:
        if adapter_probe_error is not None:
            return "node_not_found" if adapter_probe_error.get("status_code") == 404 else "probe_failed"
        if adapter_probe is None or adapter_probe.get("probe_status") != "probed":
            return "probe_failed"
        if validation_status != "validated":
            return "runtime_image_invalid"
        cpu_logical = ((measured_capabilities.get("cpu") or {}).get("logical"))
        memory_total_mb = ((measured_capabilities.get("memory") or {}).get("total_mb"))
        if cpu_logical is None or memory_total_mb is None:
            return "insufficient_evidence"
        return "sellable"

    def _recommended_offer(
        self,
        *,
        assessment_id: str,
        assessment_status: str,
        seller_user_id: str,
        compute_node_id: str | None,
        pricing_decision: dict[str, Any],
        runtime_image_ref: str,
        measured_capabilities: dict[str, Any],
        session: JoinSessionRecord,
    ) -> dict[str, Any]:
        resolved_accelerator = str(pricing_decision["resolved_accelerator"])
        title_prefix = str(LANE_RULES[resolved_accelerator]["title"])
        safe_compute_node_id = compute_node_id or "unresolved-node"
        capability_summary = {
            "cpu_limit": ((measured_capabilities.get("cpu") or {}).get("logical")),
            "memory_limit_gb": self._memory_gb_from_measured(measured_capabilities),
            "gpu_mode": "shared" if resolved_accelerator == "gpu" else None,
            "accelerator": resolved_accelerator,
            "generic_resources": list(measured_capabilities.get("generic_resources") or []),
            "warnings": list(measured_capabilities.get("warnings") or []),
        }
        return {
            "title": f"{title_prefix} ({safe_compute_node_id})",
            "seller_node_id": safe_compute_node_id,
            "compute_node_id": compute_node_id,
            "offer_profile_id": pricing_decision["offer_profile_id"],
            "runtime_image_ref": runtime_image_ref,
            "price_snapshot": dict(pricing_decision["price_snapshot"]),
            "capability_summary": capability_summary,
            "inventory_state": {
                "available": assessment_status == "sellable",
                "assessment_status": assessment_status,
                "verified_source": f"seller_onboarding_{session.status}",
                "assessment_id": assessment_id,
                "reason": None if assessment_status == "sellable" else assessment_status,
            },
        }

    @staticmethod
    def _memory_gb_from_measured(measured_capabilities: dict[str, Any]) -> int | None:
        total_mb = ((measured_capabilities.get("memory") or {}).get("total_mb"))
        if total_mb is None:
            return None
        return int(total_mb / 1024)

    @staticmethod
    def _clean_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _assessment_read(record: SellerCapabilityAssessmentRecord) -> CapabilityAssessmentRead:
        return CapabilityAssessmentRead(
            assessment_id=record.id,
            assessment_status=record.assessment_status,
            resolved_target=CapabilityAssessmentResolvedTargetRead(
                onboarding_session_id=record.onboarding_session_id,
                seller_user_id=record.seller_user_id,
                compute_node_id=record.compute_node_id,
                node_ref=record.node_ref,
            ),
            sources_used=dict(record.sources_used),
            measured_capabilities=dict(record.measured_capabilities),
            pricing_decision=dict(record.pricing_decision),
            runtime_image_validation=dict(record.runtime_image_validation),
            recommended_offer=dict(record.recommended_offer),
            warnings=list(record.warnings),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
