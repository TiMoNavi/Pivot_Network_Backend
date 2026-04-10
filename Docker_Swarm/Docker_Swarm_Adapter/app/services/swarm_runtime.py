from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from typing import Any

from app.config import Settings
from app.drivers.command import CommandExecutionError
from app.drivers.docker import DockerDriver
from app.drivers.wireguard import WireGuardDriver
from app.errors import NotImplementedYetError
from app.errors import AdapterHTTPException
from app.schemas.runtime import (
    NodeProbeRequest,
    NodeProbeResponse,
    RuntimeBundleResponse,
    RuntimeImageValidateRequest,
    RuntimeImageValidateResponse,
    RuntimeTargetNode,
    ServiceInspectRequest,
    ServiceInspectResponse,
    ServiceTaskSummary,
    ValidationCheck,
)
from app.services.swarm_nodes import SwarmNodeService
from app.services.wireguard import WireGuardService
from app.schemas.wireguard import WireGuardPeerApplyRequest, WireGuardPeerRemoveRequest


class SwarmRuntimeService:
    def __init__(
        self,
        settings: Settings,
        docker: DockerDriver,
        swarm_nodes: SwarmNodeService,
        wireguard: WireGuardDriver,
        wireguard_service: WireGuardService,
    ) -> None:
        self.settings = settings
        self.docker = docker
        self.swarm_nodes = swarm_nodes
        self.wireguard = wireguard
        self.wireguard_service = wireguard_service

    def validate_runtime_image(self, request: RuntimeImageValidateRequest) -> RuntimeImageValidateResponse:
        target = self._resolve_target_node(request.node_ref, request.compute_node_id)
        checks: list[ValidationCheck] = []

        pull_ok = True
        pull_detail = "image_pull_succeeded"
        image = None
        try:
            self.docker.image_pull(request.image_ref)
        except CommandExecutionError as exc:
            pull_ok = False
            pull_detail = exc.message
            try:
                image = self.docker.image_inspect(request.image_ref)
                pull_ok = True
                pull_detail = "image_pull_failed_but_local_image_present"
            except CommandExecutionError:
                image = None
        checks.append(ValidationCheck(name="image_pull", ok=pull_ok, detail=pull_detail))

        if image is None:
            try:
                image = self.docker.image_inspect(request.image_ref)
            except CommandExecutionError as exc:
                raise AdapterHTTPException(400, exc.message, "image_inspect_failed") from exc

        config = image.get("Config", {}) or {}
        labels = config.get("Labels", {}) or {}

        base_image_ref = labels.get(self.settings.runtime_base_image_label)
        contract_version = labels.get(self.settings.runtime_contract_version_label)
        buyer_agent_version = labels.get(self.settings.runtime_buyer_agent_label)
        base_image_ok = bool(base_image_ref) and str(base_image_ref).startswith(
            self.settings.runtime_base_image_prefix
        )
        checks.append(
            ValidationCheck(
                name="base_image_contract",
                ok=base_image_ok,
                detail="base_image_contract_ok" if base_image_ok else "missing_or_invalid_base_image_contract",
                payload={
                    "base_image_ref": base_image_ref,
                    "expected_prefix": self.settings.runtime_base_image_prefix,
                },
            )
        )

        contract_version_ok = contract_version == self.settings.runtime_contract_version
        checks.append(
            ValidationCheck(
                name="runtime_contract_version",
                ok=contract_version_ok,
                detail="runtime_contract_version_ok" if contract_version_ok else "runtime_contract_version_mismatch",
                payload={
                    "runtime_contract_version": contract_version,
                    "expected": self.settings.runtime_contract_version,
                },
            )
        )

        buyer_agent_ok = buyer_agent_version == self.settings.runtime_buyer_agent_version
        checks.append(
            ValidationCheck(
                name="buyer_runtime_agent",
                ok=buyer_agent_ok,
                detail="buyer_runtime_agent_ok" if buyer_agent_ok else "buyer_runtime_agent_missing_or_mismatch",
                payload={
                    "buyer_runtime_agent_version": buyer_agent_version,
                    "expected": self.settings.runtime_buyer_agent_version,
                },
            )
        )

        shell_path = self._detect_shell(request.image_ref)
        shell_ok = shell_path is not None
        checks.append(
            ValidationCheck(
                name="shell_available",
                ok=shell_ok,
                detail=shell_path or "missing_shell",
                payload={"shell_path": shell_path},
            )
        )

        tty_ok = shell_ok
        checks.append(
            ValidationCheck(
                name="tty_support",
                ok=tty_ok,
                detail="shell_entrypoint_available" if tty_ok else "tty_requires_shell",
            )
        )

        shell_agent_ok, shell_agent_detail = self._check_shell_agent(request.image_ref)
        checks.append(
            ValidationCheck(
                name="shell_agent",
                ok=shell_agent_ok,
                detail=shell_agent_detail,
                payload={"shell_agent_path": self.settings.runtime_shell_agent_path},
            )
        )

        healthcheck_ok = bool(config.get("Healthcheck"))
        checks.append(
            ValidationCheck(
                name="healthcheck",
                ok=healthcheck_ok,
                detail="healthcheck_present" if healthcheck_ok else "healthcheck_missing",
                payload={"healthcheck": config.get("Healthcheck")},
            )
        )

        command_ok, command_detail = self._check_command_bootstrap(request.image_ref, shell_path)
        checks.append(
            ValidationCheck(
                name="entrypoint_command",
                ok=command_ok,
                detail=command_detail,
                payload={"entrypoint": config.get("Entrypoint"), "cmd": config.get("Cmd")},
            )
        )

        gpu_ok, gpu_detail, gpu_payload = self._check_gpu_visibility(request.image_ref, shell_path)
        checks.append(
            ValidationCheck(
                name="gpu_visibility",
                ok=gpu_ok,
                detail=gpu_detail,
                payload=gpu_payload,
            )
        )

        ports_ok = True
        exposed_ports = sorted((config.get("ExposedPorts") or {}).keys())
        checks.append(
            ValidationCheck(
                name="ports",
                ok=ports_ok,
                detail="ports_checked",
                payload={"exposed_ports": exposed_ports},
            )
        )

        validation_status = "validated" if all(check.ok for check in checks) else "validation_failed"
        validation_payload = {
            "image_id": image.get("Id"),
            "base_image_ref": base_image_ref,
            "runtime_contract_version": contract_version,
            "buyer_runtime_agent_version": buyer_agent_version,
            "managed_runtime_image_ok": validation_status == "validated",
            "labels": labels,
            "healthcheck": config.get("Healthcheck"),
            "exposed_ports": exposed_ports,
            "target_node": target.model_dump(),
        }

        return RuntimeImageValidateResponse(
            image_ref=request.image_ref,
            node=target,
            validation_status=validation_status,
            checks=checks,
            validation_payload=validation_payload,
        )

    def probe_node(self, request: NodeProbeRequest) -> NodeProbeResponse:
        target = self._resolve_target_node(request.node_ref, request.compute_node_id)
        inspect = self.swarm_nodes.get_node_inspect(target.node_id)
        description = inspect.get("Description", {}) or {}
        resources = description.get("Resources", {}) or {}
        labels = inspect.get("Spec", {}).get("Labels", {}) or {}

        capabilities: dict[str, Any] = {
            "hostname": description.get("Hostname"),
            "platform": description.get("Platform", {}),
            "cpu_logical": int(resources.get("NanoCPUs", 0) / 1_000_000_000) if resources.get("NanoCPUs") else None,
            "memory_total_mb": int(resources.get("MemoryBytes", 0) / (1024 * 1024)) if resources.get("MemoryBytes") else None,
            "generic_resources": resources.get("GenericResources", []),
            "accelerator_label": labels.get("platform.accelerator"),
            "probe_source": "docker_node_inspect",
        }
        warnings: list[str] = []

        if target.node_id == self.docker.info().get("NodeID"):
            capabilities.update(self._local_host_probe())
        else:
            warnings.append("local_host_probe_not_available_for_remote_node")

        probe_status = "probed"
        if not capabilities.get("cpu_logical") or not capabilities.get("memory_total_mb"):
            probe_status = "probe_failed"
            warnings.append("missing_cpu_or_memory_capacity")

        if capabilities.get("host_probe", {}).get("gpu", {}).get("present") is False:
            warnings.append("gpu_probe_unavailable_or_no_gpu_detected")

        return NodeProbeResponse(
            node=target,
            probe_status=probe_status,
            probe_measured_capabilities=capabilities,
            warnings=warnings,
        )

    def inspect_service(self, request: ServiceInspectRequest) -> ServiceInspectResponse:
        try:
            service = self.docker.service_inspect(request.service_name)
        except CommandExecutionError as exc:
            raise AdapterHTTPException(404, exc.message, "service_not_found") from exc

        tasks = self.docker.service_ps(request.service_name)
        logs_summary = self._service_logs_summary(request.service_name)
        recent_errors = self._service_recent_errors(tasks)
        ports = service.get("Endpoint", {}).get("Ports") or []
        mode = self._service_mode(service)

        task_summaries = [
            ServiceTaskSummary(
                id=task.get("ID"),
                name=str(task.get("Name") or ""),
                image=task.get("Image"),
                node=task.get("Node"),
                desired_state=str(task.get("DesiredState") or ""),
                current_state=str(task.get("CurrentState") or ""),
                error=task.get("Error") or None,
            )
            for task in tasks
        ]

        status = "running" if any("running" in str(task.get("CurrentState", "")).lower() for task in tasks) else "degraded"

        return ServiceInspectResponse(
            service_id=str(service.get("ID") or ""),
            service_name=str(service.get("Spec", {}).get("Name") or request.service_name),
            image=str(service.get("Spec", {}).get("TaskTemplate", {}).get("ContainerSpec", {}).get("Image") or ""),
            mode=mode,
            status=status,
            ports=ports,
            tasks=task_summaries,
            recent_error_summary=recent_errors,
            logs_summary=logs_summary,
            raw_payload=service,
        )

    def create_runtime_bundle(self, request) -> RuntimeBundleResponse:
        target = self._resolve_target_node(request.node_ref, request.compute_node_id)
        target_inspect = self.swarm_nodes.get_node_inspect(target.node_id)
        self._ensure_runtime_target_is_eligible(target_inspect)

        validation = self.validate_runtime_image(
            RuntimeImageValidateRequest(
                image_ref=request.runtime_image_ref,
                node_ref=target.node_id,
            )
        )
        if validation.validation_status != "validated":
            raise AdapterHTTPException(
                409,
                "runtime_image_validation_failed_for_bundle_create",
                "runtime_image_validation_failed",
            )

        names = self._bundle_names(request.session_id)
        if self.docker.service_exists(names["runtime_service_name"]) or self.docker.service_exists(
            names["gateway_service_name"]
        ):
            raise AdapterHTTPException(409, "runtime_bundle_already_exists", "runtime_bundle_exists")
        if self.docker.network_exists(names["network_name"]):
            raise AdapterHTTPException(409, "runtime_bundle_network_already_exists", "runtime_bundle_exists")

        self.docker.network_create(
            names["network_name"],
            labels={
                "pivot.bundle": "runtime-session",
                "pivot.session_id": request.session_id,
            },
        )

        try:
            runtime_service = self.docker.service_create(
                name=names["runtime_service_name"],
                image=request.runtime_image_ref,
                labels=self._bundle_common_labels(
                    session_id=request.session_id,
                    offer_id=request.offer_id,
                    role="runtime",
                    compute_node_id=target.compute_node_id,
                ),
                env={
                    "PIVOT_SESSION_ID": request.session_id,
                    "PIVOT_OFFER_ID": request.offer_id,
                    "PIVOT_SHELL_AGENT_PORT": str(self.settings.runtime_shell_agent_port),
                },
                constraints=[f"node.id=={target.node_id}"],
                networks=[names["network_name"]],
            )

            gateway_port = self._allocate_gateway_published_port()
            manager_node_id = str(self.docker.info().get("NodeID") or "")
            gateway_constraints = [f"node.id=={manager_node_id}"] if manager_node_id else None
            runtime_upstream = self._runtime_service_upstream(runtime_service, names["network_name"], names["runtime_service_name"])
            gateway_service = self.docker.service_create(
                name=names["gateway_service_name"],
                image=self.settings.gateway_image,
                labels=self._bundle_common_labels(
                    session_id=request.session_id,
                    offer_id=request.offer_id,
                    role="gateway",
                    compute_node_id=target.compute_node_id,
                ),
                constraints=gateway_constraints,
                networks=[names["network_name"]],
                entrypoint="caddy",
                published_port=gateway_port,
                target_port=self.settings.gateway_target_port,
                publish_mode="host",
                args=[
                    "reverse-proxy",
                    "--from",
                    f":{self.settings.gateway_target_port}",
                    "--to",
                    f"http://{runtime_upstream}:{self.settings.runtime_shell_agent_port}",
                ],
            )
        except Exception:
            self._cleanup_partial_bundle(names)
            raise

        wireguard_metadata: dict[str, Any] | None = None
        if str(request.network_mode).lower() == "wireguard":
            public_key = str(request.buyer_network.get("public_key") or "").strip()
            if not public_key:
                self._cleanup_partial_bundle(names)
                raise AdapterHTTPException(
                    400,
                    "buyer_wireguard_public_key_required",
                    "wireguard_invalid_request",
                )
            try:
                wireguard_metadata = self.wireguard_service.apply_peer(
                    WireGuardPeerApplyRequest(
                        lease_type="buyer",
                        runtime_session_id=request.session_id,
                        peer_payload=request.buyer_network,
                    )
                ).model_dump()
            except Exception:
                self._cleanup_partial_bundle(names)
                raise

        return self._bundle_response(
            session_id=request.session_id,
            status="created",
            runtime_service=runtime_service,
            gateway_service=gateway_service,
            network_name=names["network_name"],
            wireguard_metadata_override=wireguard_metadata,
        )

    def inspect_runtime_bundle(self, request) -> RuntimeBundleResponse:
        names = self._bundle_names(request.session_id)
        runtime_service = self._inspect_service_if_exists(names["runtime_service_name"])
        gateway_service = self._inspect_service_if_exists(names["gateway_service_name"])
        network_name = names["network_name"] if self.docker.network_exists(names["network_name"]) else None

        if runtime_service is None and gateway_service is None and network_name is None:
            raise AdapterHTTPException(404, "runtime_bundle_not_found", "runtime_bundle_not_found")

        status = "partial"
        if runtime_service and gateway_service:
            status = "running"
        elif runtime_service or gateway_service:
            status = "partial"
        elif network_name:
            status = "allocated"

        return self._bundle_response(
            session_id=request.session_id,
            status=status,
            runtime_service=runtime_service,
            gateway_service=gateway_service,
            network_name=network_name,
            wireguard_metadata_override=self._wireguard_lease_for_session(request.session_id),
        )

    def remove_runtime_bundle(self, request) -> RuntimeBundleResponse:
        names = self._bundle_names(request.session_id)
        runtime_service = self._inspect_service_if_exists(names["runtime_service_name"])
        gateway_service = self._inspect_service_if_exists(names["gateway_service_name"])
        network_exists = self.docker.network_exists(names["network_name"])

        if runtime_service is None and gateway_service is None and not network_exists:
            raise AdapterHTTPException(404, "runtime_bundle_not_found", "runtime_bundle_not_found")

        recent_errors: list[str] = []
        wireguard_metadata = self._wireguard_lease_for_session(request.session_id)

        if wireguard_metadata and wireguard_metadata.get("lease_type") == "buyer":
            try:
                wireguard_metadata = self.wireguard_service.remove_peer(
                    WireGuardPeerRemoveRequest(
                        runtime_session_id=request.session_id,
                        lease_type="buyer",
                    )
                ).model_dump()
            except AdapterHTTPException as exc:
                recent_errors.append(str(exc.detail))
                if not request.force:
                    raise

        if gateway_service is not None:
            try:
                self.docker.service_rm(names["gateway_service_name"])
                self.docker.wait_for_service_removal(names["gateway_service_name"])
            except CommandExecutionError as exc:
                recent_errors.append(exc.message)
                if not request.force:
                    raise AdapterHTTPException(409, exc.message, "runtime_bundle_remove_failed")

        if runtime_service is not None:
            try:
                self.docker.service_rm(names["runtime_service_name"])
                self.docker.wait_for_service_removal(names["runtime_service_name"])
            except CommandExecutionError as exc:
                recent_errors.append(exc.message)
                if not request.force:
                    raise AdapterHTTPException(409, exc.message, "runtime_bundle_remove_failed")

        if network_exists:
            removed = False
            for _ in range(10):
                try:
                    self.docker.network_rm(names["network_name"])
                    self.docker.wait_for_network_removal(names["network_name"])
                    removed = True
                    break
                except CommandExecutionError as exc:
                    recent_errors.append(exc.message)
                    time.sleep(0.5)
            if not removed and not request.force:
                raise AdapterHTTPException(409, "runtime_bundle_network_remove_failed", "runtime_bundle_remove_failed")

        return RuntimeBundleResponse(
            session_id=request.session_id,
            status="removed",
            runtime_service_name=names["runtime_service_name"],
            gateway_service_name=names["gateway_service_name"],
            network_name=names["network_name"],
            connect_metadata={},
            wireguard_lease_metadata=wireguard_metadata or self._wireguard_metadata(status="removed"),
            recent_error_summary=list(dict.fromkeys(recent_errors)),
        )

    def _resolve_target_node(self, node_ref: str | None, compute_node_id: str | None) -> RuntimeTargetNode:
        if compute_node_id:
            inspect = self.swarm_nodes.get_node_inspect_by_compute_node_id(compute_node_id)
        elif node_ref:
            inspect = self.swarm_nodes.get_node_inspect(node_ref)
        else:
            inspect = self.swarm_nodes.get_node_inspect("self")

        labels = inspect.get("Spec", {}).get("Labels", {}) or {}
        return RuntimeTargetNode(
            node_id=str(inspect.get("ID") or ""),
            hostname=str(inspect.get("Description", {}).get("Hostname") or ""),
            role=str(inspect.get("Spec", {}).get("Role") or ""),
            status=str(inspect.get("Status", {}).get("State") or "").lower(),
            availability=str(inspect.get("Spec", {}).get("Availability") or "").lower(),
            compute_node_id=labels.get("platform.compute_node_id"),
        )

    def _ensure_runtime_target_is_eligible(self, inspect: dict[str, Any]) -> None:
        labels = inspect.get("Spec", {}).get("Labels", {}) or {}
        hostname = inspect.get("Description", {}).get("Hostname", inspect.get("ID", "node"))
        role = inspect.get("Spec", {}).get("Role")
        status = str(inspect.get("Status", {}).get("State") or "").lower()
        availability = str(inspect.get("Spec", {}).get("Availability") or "").lower()

        if role != "worker":
            raise AdapterHTTPException(400, f"runtime_target_must_be_worker: {hostname}", "runtime_target_invalid")
        if status != "ready":
            raise AdapterHTTPException(400, f"runtime_target_not_ready: {hostname}", "runtime_target_invalid")
        if availability != "active":
            raise AdapterHTTPException(400, f"runtime_target_not_active: {hostname}", "runtime_target_invalid")
        if labels.get("platform.role") != "compute" or str(labels.get("platform.compute_enabled", "")).lower() != "true":
            raise AdapterHTTPException(
                400,
                f"runtime_target_not_compute_enabled: {hostname}",
                "runtime_target_invalid",
            )

    @staticmethod
    def _bundle_slug(session_id: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", session_id.strip().lower()).strip("-")
        return (slug or "session")[:40]

    def _bundle_names(self, session_id: str) -> dict[str, str]:
        slug = self._bundle_slug(session_id)
        return {
            "runtime_service_name": f"runtime-{slug}",
            "gateway_service_name": f"gateway-{slug}",
            "network_name": f"{self.settings.session_network_prefix}-{slug}",
        }

    @staticmethod
    def _bundle_common_labels(
        session_id: str,
        offer_id: str,
        role: str,
        compute_node_id: str | None,
    ) -> dict[str, str]:
        labels = {
            "pivot.bundle": "runtime-session",
            "pivot.session_id": session_id,
            "pivot.offer_id": offer_id,
            "pivot.role": role,
        }
        if compute_node_id:
            labels["pivot.compute_node_id"] = compute_node_id
        return labels

    def _allocate_gateway_published_port(self) -> int:
        used_ports: set[int] = set()
        for service in self.docker.service_ls():
            try:
                inspect = self.docker.service_inspect(service["Name"])
            except CommandExecutionError:
                continue
            for port in inspect.get("Endpoint", {}).get("Ports") or []:
                published = port.get("PublishedPort")
                if published:
                    used_ports.add(int(published))

        for port in range(self.settings.gateway_published_port_start, self.settings.gateway_published_port_end + 1):
            if port not in used_ports:
                return port
        raise AdapterHTTPException(409, "no_free_gateway_port_available", "runtime_bundle_create_failed")

    def _inspect_service_if_exists(self, service_name: str) -> dict[str, Any] | None:
        try:
            return self.docker.service_inspect(service_name)
        except CommandExecutionError:
            return None

    def _bundle_service_summary(self, service: dict[str, Any] | None) -> dict[str, Any] | None:
        if service is None:
            return None
        service_name = service.get("Spec", {}).get("Name", "")
        try:
            tasks = self.docker.service_ps(service_name)
        except CommandExecutionError:
            return None
        return {
            "service_name": service_name,
            "service_id": service.get("ID"),
            "image": service.get("Spec", {}).get("TaskTemplate", {}).get("ContainerSpec", {}).get("Image"),
            "tasks": [
                {
                    "id": task.get("ID"),
                    "name": task.get("Name"),
                    "node": task.get("Node"),
                    "desired_state": task.get("DesiredState"),
                    "current_state": task.get("CurrentState"),
                    "error": task.get("Error") or None,
                }
                for task in tasks
            ],
            "ports": service.get("Endpoint", {}).get("Ports") or [],
        }

    @staticmethod
    def _runtime_service_upstream(
        runtime_service: dict[str, Any],
        network_name: str,
        default_service_name: str,
    ) -> str:
        for vip in runtime_service.get("Endpoint", {}).get("VirtualIPs") or []:
            network_id = vip.get("NetworkID")
            addr = str(vip.get("Addr") or "")
            if not addr:
                continue
            ip = addr.split("/", 1)[0]
            if ip and network_id:
                return ip
        return default_service_name

    def _connect_metadata(
        self,
        gateway_service: dict[str, Any] | None,
        network_name: str | None,
        wireguard_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if gateway_service is None:
            return {}
        ports = gateway_service.get("Endpoint", {}).get("Ports") or []
        published_port = None
        for port in ports:
            published = port.get("PublishedPort")
            if published:
                published_port = int(published)
                break
        if published_port is None:
            return {}

        public_base_url = f"{self.settings.gateway_access_scheme}://{self.settings.swarm_manager_addr}:{published_port}/"
        wireguard_host = wireguard_metadata.get("server_access_ip") or self.settings.swarm_manager_addr
        wireguard_base_url = f"{self.settings.gateway_access_scheme}://{wireguard_host}:{published_port}/"
        shell_path = self.settings.runtime_shell_embed_path.lstrip("/")
        upload_path = self.settings.runtime_workspace_upload_path.lstrip("/")
        extract_path = self.settings.runtime_workspace_extract_path.lstrip("/")
        status_path = self.settings.runtime_workspace_status_path.lstrip("/")

        return {
            "access_mode": "web_terminal",
            "gateway_access_url": public_base_url,
            "gateway_host": self.settings.swarm_manager_addr,
            "gateway_port": published_port,
            "public_gateway_access_url": public_base_url,
            "wireguard_gateway_access_url": wireguard_base_url,
            "wireguard_gateway_host": wireguard_host,
            "wireguard_gateway_port": published_port,
            "shell_embed_url": f"{wireguard_base_url}{shell_path}",
            "public_shell_embed_url": f"{public_base_url}{shell_path}",
            "wireguard_shell_embed_url": f"{wireguard_base_url}{shell_path}",
            "workspace_sync_url": f"{wireguard_base_url}{upload_path}",
            "public_workspace_sync_url": f"{public_base_url}{upload_path}",
            "wireguard_workspace_sync_url": f"{wireguard_base_url}{upload_path}",
            "workspace_extract_url": f"{wireguard_base_url}{extract_path}",
            "workspace_status_url": f"{wireguard_base_url}{status_path}",
            "workspace_root": self.settings.runtime_workspace_root,
            "network_name": network_name,
            "server_public_key": wireguard_metadata.get("server_public_key"),
            "server_access_ip": wireguard_metadata.get("server_access_ip"),
            "endpoint_host": wireguard_metadata.get("endpoint_host"),
            "endpoint_port": wireguard_metadata.get("endpoint_port"),
            "allowed_ips": wireguard_metadata.get("allowed_ips", []),
            "client_allowed_ips": wireguard_metadata.get("client_allowed_ips", []),
            "persistent_keepalive": wireguard_metadata.get("persistent_keepalive"),
            "client_address": wireguard_metadata.get("client_address"),
        }

    def _wireguard_metadata(self, status: str) -> dict[str, Any]:
        try:
            output = self.wireguard.show()
            config = self.wireguard.read_config()
        except Exception:  # noqa: BLE001
            return {
                "status": status,
                "server_interface": self.settings.wireguard_interface,
            }

        public_key = None
        listen_port = None
        current_interface = None
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("interface:"):
                current_interface = stripped.split(":", 1)[1].strip()
            elif current_interface == self.settings.wireguard_interface and stripped.startswith("public key:"):
                public_key = stripped.split(":", 1)[1].strip()
            elif current_interface == self.settings.wireguard_interface and stripped.startswith("listening port:"):
                listen_port = int(stripped.split(":", 1)[1].strip())

        allowed_ips: list[str] = []
        for line in config.splitlines():
            stripped = line.strip()
            if stripped.startswith("Address ="):
                allowed_ips = [item.strip() for item in stripped.split("=", 1)[1].split(",") if item.strip()]
                break

        return {
            "status": status,
            "server_interface": self.settings.wireguard_interface,
            "server_public_key": public_key,
            "server_access_ip": self._wireguard_server_access_ip(config),
            "endpoint_host": self.settings.swarm_manager_addr,
            "endpoint_port": listen_port,
            "allowed_ips": allowed_ips,
            "persistent_keepalive": 25,
        }

    def _bundle_response(
        self,
        *,
        session_id: str,
        status: str,
        runtime_service: dict[str, Any] | None,
        gateway_service: dict[str, Any] | None,
        network_name: str | None,
        wireguard_metadata_override: dict[str, Any] | None = None,
    ) -> RuntimeBundleResponse:
        runtime_summary = self._bundle_service_summary(runtime_service)
        gateway_summary = self._bundle_service_summary(gateway_service)
        recent_errors: list[str] = []
        for summary in (runtime_summary, gateway_summary):
            if not summary:
                continue
            for task in summary["tasks"]:
                if task.get("error"):
                    recent_errors.append(str(task["error"]))
                current_state = str(task.get("current_state") or "")
                if any(token in current_state.lower() for token in ("failed", "rejected", "shutdown")):
                    recent_errors.append(current_state)

        wireguard_metadata = wireguard_metadata_override or self._wireguard_lease_for_session(session_id)
        if wireguard_metadata is None:
            wireguard_metadata = self._wireguard_metadata(status="pending_implementation")

        return RuntimeBundleResponse(
            session_id=session_id,
            status=self._bundle_runtime_status(status, runtime_summary, gateway_summary, recent_errors),
            runtime_service_name=runtime_summary["service_name"] if runtime_summary else None,
            gateway_service_name=gateway_summary["service_name"] if gateway_summary else None,
            network_name=network_name,
            runtime_service=runtime_summary,
            gateway_service=gateway_summary,
            connect_metadata=self._connect_metadata(gateway_service, network_name, wireguard_metadata),
            wireguard_lease_metadata=wireguard_metadata,
            recent_error_summary=list(dict.fromkeys(recent_errors))[:10],
        )

    def _wireguard_lease_for_session(self, session_id: str) -> dict[str, Any] | None:
        peer = self.wireguard_service.get_peer(runtime_session_id=session_id, lease_type="buyer")
        if peer is None:
            return None
        return peer.model_dump()

    @staticmethod
    def _bundle_runtime_status(
        requested_status: str,
        runtime_summary: dict[str, Any] | None,
        gateway_summary: dict[str, Any] | None,
        recent_errors: list[str],
    ) -> str:
        if requested_status == "removed":
            return "removed"
        if recent_errors:
            return "failed"

        task_states: list[str] = []
        for summary in (runtime_summary, gateway_summary):
            if not summary:
                continue
            for task in summary["tasks"]:
                task_states.append(str(task.get("current_state") or "").lower())

        if task_states and all("running" in state for state in task_states):
            return "running"
        if runtime_summary or gateway_summary:
            return "provisioning"
        return requested_status

    def _cleanup_partial_bundle(self, names: dict[str, str]) -> None:
        for service_name in (names["gateway_service_name"], names["runtime_service_name"]):
            if self.docker.service_exists(service_name):
                try:
                    self.docker.service_rm(service_name)
                    self.docker.wait_for_service_removal(service_name)
                except CommandExecutionError:
                    pass
        if self.docker.network_exists(names["network_name"]):
            try:
                self.docker.network_rm(names["network_name"])
                self.docker.wait_for_network_removal(names["network_name"])
            except CommandExecutionError:
                pass

    def _detect_shell(self, image_ref: str) -> str | None:
        for shell_path in ("/bin/bash", "/bin/sh"):
            try:
                self.docker.run_container_check(image_ref, shell_path, ["-lc", "echo shell-ok"])
                return shell_path
            except CommandExecutionError:
                continue
        return None

    def _check_shell_agent(self, image_ref: str) -> tuple[bool, str]:
        shell_path = self._detect_shell(image_ref)
        if shell_path is None:
            return False, "shell_missing"
        command = f"test -x {self.settings.runtime_shell_agent_path} && echo agent-ok"
        try:
            output = self.docker.run_container_check(image_ref, shell_path, ["-lc", command])
            if "agent-ok" in output:
                return True, "shell_agent_present"
            return False, "shell_agent_missing"
        except CommandExecutionError:
            return False, "shell_agent_missing"

    def _check_command_bootstrap(self, image_ref: str, shell_path: str | None) -> tuple[bool, str]:
        if shell_path is None:
            return False, "shell_missing"
        try:
            self.docker.run_container_check(image_ref, shell_path, ["-lc", "echo bootstrap-ok"])
            return True, "command_bootstrap_ok"
        except CommandExecutionError as exc:
            return False, exc.message

    def _check_gpu_visibility(
        self,
        image_ref: str,
        shell_path: str | None,
    ) -> tuple[bool, str, dict[str, Any]]:
        has_nvidia_smi = shutil.which("nvidia-smi") is not None
        if not has_nvidia_smi:
            return True, "gpu_probe_skipped_host_has_no_nvidia_smi", {"host_has_nvidia_smi": False}

        if shell_path is None:
            return False, "gpu_probe_failed_shell_missing", {"host_has_nvidia_smi": True}

        try:
            output = self.docker.run_container_check(
                image_ref,
                shell_path,
                ["-lc", "command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L || echo nvidia-smi-unavailable"],
            )
            lines = [line for line in output.splitlines() if line.strip()]
            ok = not any("unavailable" in line for line in lines)
            return ok, "gpu_visibility_checked", {"host_has_nvidia_smi": True, "output": lines}
        except CommandExecutionError as exc:
            return False, exc.message, {"host_has_nvidia_smi": True}

    def _local_host_probe(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"probe_source": "local_host_probe"}
        payload["lscpu"] = self._run_host_json_command(["lscpu", "-J"])
        payload["disk"] = self._run_host_json_command(["lsblk", "-J", "-b"])
        payload["gpu"] = self._run_gpu_probe()
        return payload

    @staticmethod
    def _run_host_json_command(command: list[str]) -> dict[str, Any] | None:
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
        except (subprocess.TimeoutExpired, OSError):
            return None
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _run_gpu_probe() -> dict[str, Any]:
        if shutil.which("nvidia-smi") is None:
            return {"present": False}
        try:
            completed = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError):
            return {"present": False}
        if completed.returncode != 0:
            return {"present": False, "detail": completed.stderr.strip() or "nvidia-smi_failed"}
        gpus = []
        for line in completed.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 3:
                gpus.append(
                    {
                        "name": parts[0],
                        "memory_total_mb": parts[1],
                        "driver_version": parts[2],
                    }
                )
        return {"present": bool(gpus), "devices": gpus}

    @staticmethod
    def _service_mode(service: dict[str, Any]) -> str:
        mode = service.get("Spec", {}).get("Mode", {})
        if "Global" in mode:
            return "global"
        if "Replicated" in mode:
            return "replicated"
        return "unknown"

    def _service_logs_summary(self, service_name: str) -> list[str]:
        try:
            output = self.docker.service_logs(service_name, tail=20)
        except CommandExecutionError:
            return []
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return lines[-10:]

    @staticmethod
    def _service_recent_errors(tasks: list[dict[str, Any]]) -> list[str]:
        errors: list[str] = []
        for task in tasks:
            if task.get("Error"):
                errors.append(str(task["Error"]))
            current_state = str(task.get("CurrentState") or "")
            if any(token in current_state.lower() for token in ("failed", "rejected", "shutdown")):
                errors.append(current_state)
        deduped: list[str] = []
        for item in errors:
            if item not in deduped:
                deduped.append(item)
        return deduped[:10]

    @staticmethod
    def _wireguard_server_access_ip(config_text: str) -> str | None:
        for line in config_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("Address ="):
                first = stripped.split("=", 1)[1].split(",")[0].strip()
                try:
                    return str(__import__("ipaddress").ip_interface(first).ip)
                except ValueError:
                    return None
        return None
