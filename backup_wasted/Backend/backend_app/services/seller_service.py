from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend_app.clients.adapter.client import AdapterClient
from backend_app.clients.adapter.client import AdapterClientError
from backend_app.core.config import get_settings
from backend_app.repositories.supply_repository import SupplyRepository
from backend_app.schemas.supply import ImageArtifactRead, ImageOfferRead, SellerImageReportRequest, SellerImageReportResponse
from backend_app.services.audit_service import AuditService


class SellerService:
    def __init__(
        self,
        adapter_client: AdapterClient,
        supply_repository: SupplyRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.adapter_client = adapter_client
        self.settings = get_settings()
        self.supply_repository = supply_repository
        self.audit_service = audit_service

    def get_runtime_base_images(self) -> list[dict[str, Any]]:
        return [
            {
                "image_ref": self.settings.managed_runtime_base_image,
                "contract_version": self.settings.managed_runtime_contract_version,
                "description": "Managed runtime base image with shell agent and platform contract.",
            }
        ]

    def get_runtime_contract(self) -> dict[str, Any]:
        return {
            "contract_version": self.settings.managed_runtime_contract_version,
            "base_image_prefix": self.settings.managed_runtime_base_image.split(":")[0],
            "shell_agent_path": self.settings.managed_runtime_shell_agent_path,
            "requirements": [
                "must_be_built_from_platform_base_image",
                "must_include_shell_agent",
                "must_support_tty",
                "must_pass_healthcheck",
            ],
        }

    def register_node(self, seller_user_id: str, requested_accelerator: str, requested_compute_node_id: str | None) -> dict[str, Any]:
        return self.adapter_client.get_join_material(
            {
                "seller_user_id": seller_user_id,
                "requested_accelerator": requested_accelerator,
                "requested_compute_node_id": requested_compute_node_id,
            }
        )

    def list_nodes(self, seller_user_id: str) -> list[dict[str, Any]]:
        payload = self.adapter_client.list_nodes()
        nodes = payload.get("nodes", [])
        return [
            self._decorate_node_summary(node)
            for node in nodes
            if str(node.get("seller_user_id") or "") == seller_user_id
        ]

    def get_node(self, seller_user_id: str, node_ref: str) -> dict[str, Any]:
        payload = self.adapter_client.inspect_node({"node_ref": node_ref})
        node = payload.get("node", {})
        owner = str(node.get("seller_user_id") or "")
        if owner and owner != seller_user_id:
            raise ValueError("Seller does not own this node.")
        payload["node"] = self._decorate_node_summary(node)
        return payload

    def get_claim_status(self, seller_user_id: str, node_ref: str) -> dict[str, Any]:
        payload = self.get_node(seller_user_id, node_ref)
        node = payload.get("node", {})
        claimed = (
            node.get("platform_role") == "compute"
            and bool(node.get("compute_enabled"))
            and str(node.get("seller_user_id") or "") == seller_user_id
        )
        return {
            "node_ref": node_ref,
            "claimed": claimed,
            "node": node,
        }

    def _decorate_node_summary(self, node: dict[str, Any]) -> dict[str, Any]:
        expected_wireguard_addr = self.settings.seller_compute_swarm_advertise_addr
        node_addr = node.get("node_addr")
        return {
            **node,
            "expected_wireguard_addr": expected_wireguard_addr,
            "wireguard_addr_match": bool(node_addr) and node_addr == expected_wireguard_addr,
            "network_mode": self.settings.seller_compute_network_mode,
        }

    def report_image(self, seller_user_id: str, payload: SellerImageReportRequest) -> SellerImageReportResponse:
        if self.supply_repository is None:
            raise RuntimeError("SupplyRepository is required for image reporting.")

        node_payload = self.get_node(seller_user_id, payload.node_ref)
        node = node_payload["node"]
        if (
            node.get("platform_role") != "compute"
            or not bool(node.get("compute_enabled"))
            or str(node.get("seller_user_id") or "") != seller_user_id
        ):
            raise ValueError("Seller image must be reported against a claimed compute node.")
        validate_result = self.adapter_client.validate_runtime_image(
            {"image_ref": payload.runtime_image_ref, "node_ref": payload.node_ref}
        )
        probe_result = self.adapter_client.probe_node({"node_ref": payload.node_ref})

        artifact = self.supply_repository.create_image_artifact(
            seller_user_id=seller_user_id,
            swarm_node_id=node["id"],
            repository=payload.repository,
            tag=payload.tag,
            digest=payload.digest,
            registry=payload.registry,
            base_image_ref=(validate_result.get("validation_payload") or {}).get("base_image_ref"),
            runtime_contract_version=(validate_result.get("validation_payload") or {}).get("runtime_contract_version"),
            status="reported",
        )

        offer_status = "offer_ready"
        validation_status = validate_result.get("validation_status")
        probe_status = probe_result.get("probe_status")
        if validation_status != "validated":
            offer_status = "validation_failed"
        elif probe_status not in {"probed", "success"}:
            offer_status = "probe_failed"

        offer = self.supply_repository.create_or_update_offer(
            artifact,
            seller_user_id=seller_user_id,
            swarm_node_id=node["id"],
            runtime_image_ref=payload.runtime_image_ref,
            offer_status=offer_status,
            validation_status=validation_status,
            validation_payload=validate_result.get("validation_payload"),
            validation_error=None if validation_status == "validated" else "validation_failed",
            last_validated_at=datetime.now(UTC),
            shell_agent_status=self._shell_agent_status(validate_result),
            runtime_contract_version=(validate_result.get("validation_payload") or {}).get("runtime_contract_version"),
            probe_status=probe_status,
            probe_measured_capabilities=probe_result.get("probe_measured_capabilities"),
            last_probed_at=datetime.now(UTC),
        )

        self.supply_repository.add_capability_snapshot(
            swarm_node_id=node["id"],
            cpu_logical=(probe_result.get("probe_measured_capabilities") or {}).get("cpu_logical"),
            memory_total_mb=(probe_result.get("probe_measured_capabilities") or {}).get("memory_total_mb"),
            gpu_payload=(probe_result.get("probe_measured_capabilities") or {}).get("host_probe", {}).get("gpu")
            or (probe_result.get("probe_measured_capabilities") or {}).get("gpu_payload"),
            probe_source=(probe_result.get("probe_measured_capabilities") or {}).get("probe_source"),
            probed_at=datetime.now(UTC),
        )

        if self.audit_service is not None:
            self.audit_service.log_activity(
                actor_user_id=seller_user_id,
                actor_role="seller",
                event_type="seller_image_reported",
                target_type="image_artifact",
                target_id=str(artifact.id),
                payload={
                    "runtime_image_ref": payload.runtime_image_ref,
                    "offer_status": offer.offer_status,
                },
            )

        return SellerImageReportResponse(
            artifact=ImageArtifactRead(
                id=str(artifact.id),
                seller_user_id=artifact.seller_user_id,
                swarm_node_id=artifact.swarm_node_id,
                repository=artifact.repository,
                tag=artifact.tag,
                digest=artifact.digest,
                registry=artifact.registry,
                base_image_ref=artifact.base_image_ref,
                runtime_contract_version=artifact.runtime_contract_version,
                status=artifact.status,
                created_at=artifact.created_at,
            ),
            offer=ImageOfferRead(
                id=str(offer.id),
                seller_user_id=offer.seller_user_id,
                swarm_node_id=offer.swarm_node_id,
                image_artifact_id=str(offer.image_artifact_id),
                runtime_image_ref=offer.runtime_image_ref,
                offer_status=offer.offer_status,
                validation_status=offer.validation_status,
                validation_payload=offer.validation_payload,
                validation_error=offer.validation_error,
                shell_agent_status=offer.shell_agent_status,
                probe_status=offer.probe_status,
                probe_measured_capabilities=offer.probe_measured_capabilities,
                last_validated_at=offer.last_validated_at,
                last_probed_at=offer.last_probed_at,
            ),
            validate_result=validate_result,
            probe_result=probe_result,
        )

    def list_images(self, seller_user_id: str) -> list[ImageArtifactRead]:
        if self.supply_repository is None:
            return []
        rows = self.supply_repository.list_artifacts_for_seller(seller_user_id)
        return [
            ImageArtifactRead(
                id=str(row.id),
                seller_user_id=row.seller_user_id,
                swarm_node_id=row.swarm_node_id,
                repository=row.repository,
                tag=row.tag,
                digest=row.digest,
                registry=row.registry,
                base_image_ref=row.base_image_ref,
                runtime_contract_version=row.runtime_contract_version,
                status=row.status,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def list_offers(self, seller_user_id: str) -> list[ImageOfferRead]:
        if self.supply_repository is None:
            return []
        rows = self.supply_repository.list_offers_for_seller(seller_user_id)
        return [
            ImageOfferRead(
                id=str(row.id),
                seller_user_id=row.seller_user_id,
                swarm_node_id=row.swarm_node_id,
                image_artifact_id=str(row.image_artifact_id),
                runtime_image_ref=row.runtime_image_ref,
                offer_status=row.offer_status,
                validation_status=row.validation_status,
                validation_payload=row.validation_payload,
                validation_error=row.validation_error,
                shell_agent_status=row.shell_agent_status,
                probe_status=row.probe_status,
                probe_measured_capabilities=row.probe_measured_capabilities,
                last_validated_at=row.last_validated_at,
                last_probed_at=row.last_probed_at,
            )
            for row in rows
        ]

    @staticmethod
    def _shell_agent_status(validate_result: dict[str, Any]) -> str:
        for check in validate_result.get("checks", []):
            if check.get("name") == "shell_agent":
                return "present" if check.get("ok") else "missing"
        return "unknown"
