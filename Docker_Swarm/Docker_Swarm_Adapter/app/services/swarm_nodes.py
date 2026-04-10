from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.drivers.command import CommandExecutionError
from app.drivers.docker import DockerDriver
from app.errors import AdapterHTTPException
from app.schemas.swarm import (
    AvailabilityRequest,
    AvailabilityResponse,
    ClaimRequest,
    ClaimResponse,
    JoinMaterialRequest,
    JoinMaterialResponse,
    NodeInspectRequest,
    NodeInspectResponse,
    NodeSearchResponse,
    NodeSummary,
    NodeTaskSummary,
    RemoveRequest,
    RemoveResponse,
    ServiceSummary,
    SwarmNodesResponse,
    SwarmOverviewResponse,
    SwarmStateSummary,
)


PLATFORM_LABEL_KEYS = [
    "platform.managed",
    "platform.role",
    "platform.control_plane",
    "platform.compute_enabled",
    "platform.compute_node_id",
    "platform.seller_user_id",
    "platform.accelerator",
]


class SwarmNodeService:
    def __init__(self, settings: Settings, docker: DockerDriver) -> None:
        self.settings = settings
        self.docker = docker

    def get_overview(self) -> SwarmOverviewResponse:
        swarm_info = self._swarm_info()
        manager_node = self.docker.node_inspect(swarm_info["NodeID"])
        node_summaries = self._list_node_summaries()
        services = [
            ServiceSummary(
                id=item.get("ID", ""),
                name=item.get("Name", ""),
                mode=item.get("Mode", ""),
                replicas=item.get("Replicas", ""),
                image=item.get("Image", ""),
                ports=item.get("Ports") or None,
            )
            for item in self.docker.service_ls()
        ]
        return SwarmOverviewResponse(
            manager_host=manager_node.get("Description", {}).get("Hostname", self.settings.swarm_manager_addr),
            swarm=SwarmStateSummary(
                state=str(swarm_info.get("LocalNodeState") or "unknown").lower(),
                node_id=str(swarm_info.get("NodeID") or ""),
                node_addr=str(swarm_info.get("NodeAddr") or self.settings.swarm_control_addr),
                control_available=bool(swarm_info.get("ControlAvailable")),
                nodes=int(swarm_info.get("Nodes") or 0),
                managers=int(swarm_info.get("Managers") or 0),
            ),
            node_list_summary=node_summaries,
            service_list_summary=services,
        )

    def list_nodes(self) -> SwarmNodesResponse:
        return SwarmNodesResponse(nodes=self._list_node_summaries())

    def inspect_node(self, request: NodeInspectRequest) -> NodeInspectResponse:
        node_id = self._resolve_node_ref(request.node_ref)
        inspect = self.docker.node_inspect(node_id)
        return self._node_inspect_response_from_inspect(inspect, node_id=node_id)

    def inspect_node_by_compute_node_id(self, compute_node_id: str) -> NodeInspectResponse:
        inspect = self.get_node_inspect_by_compute_node_id(compute_node_id)
        node_id = str(inspect.get("ID") or "")
        return self._node_inspect_response_from_inspect(inspect, node_id=node_id)

    def search_nodes(
        self,
        *,
        query: str | None = None,
        seller_user_id: str | None = None,
        compute_node_id: str | None = None,
        role: str | None = None,
        status: str | None = None,
        availability: str | None = None,
        accelerator: str | None = None,
        compute_enabled: bool | None = None,
    ) -> NodeSearchResponse:
        summaries = self._list_node_summaries()
        normalized_query = (query or "").strip().lower()

        def matches(summary: NodeSummary) -> bool:
            if seller_user_id and (summary.seller_user_id or "") != seller_user_id:
                return False
            if compute_node_id and (summary.compute_node_id or "") != compute_node_id:
                return False
            if role and summary.role.lower() != role.lower():
                return False
            if status and summary.status.lower() != status.lower():
                return False
            if availability and summary.availability.lower() != availability.lower():
                return False
            if accelerator and (summary.accelerator or "").lower() != accelerator.lower():
                return False
            if compute_enabled is not None and summary.compute_enabled != compute_enabled:
                return False
            if normalized_query:
                haystack = " ".join(
                    [
                        summary.id,
                        summary.hostname,
                        summary.node_addr or "",
                        summary.platform_role or "",
                        summary.compute_node_id or "",
                        summary.seller_user_id or "",
                        summary.accelerator or "",
                    ]
                ).lower()
                if normalized_query not in haystack:
                    return False
            return True

        filtered = [summary for summary in summaries if matches(summary)]
        applied_filters = {
            key: value
            for key, value in {
                "seller_user_id": seller_user_id,
                "compute_node_id": compute_node_id,
                "role": role,
                "status": status,
                "availability": availability,
                "accelerator": accelerator,
                "compute_enabled": compute_enabled,
            }.items()
            if value is not None
        }
        return NodeSearchResponse(
            nodes=filtered,
            total=len(filtered),
            query=query,
            applied_filters=applied_filters,
        )

    def _node_inspect_response_from_inspect(
        self,
        inspect: dict[str, Any],
        *,
        node_id: str,
    ) -> NodeInspectResponse:
        tasks = self.docker.node_ps(node_id)
        summary = self._node_summary_from_inspect(inspect, running_tasks=self._running_task_count(tasks))
        raw_labels = inspect.get("Spec", {}).get("Labels", {}) or {}
        platform_labels = {k: v for k, v in raw_labels.items() if k.startswith("platform.")}
        task_summaries = [self._task_summary(task) for task in tasks]
        return NodeInspectResponse(
            node=summary,
            platform_labels=platform_labels,
            raw_labels=raw_labels,
            tasks=task_summaries,
            recent_error_summary=self._recent_error_summary(tasks),
        )

    def get_join_material(self, request: JoinMaterialRequest) -> JoinMaterialResponse:
        join_token = self.docker.swarm_join_token("worker")
        manager_addr = self.settings.swarm_control_addr
        manager_port = 2377
        compute_node_id = self._recommended_compute_node_id(
            seller_user_id=request.seller_user_id,
            requested=request.requested_compute_node_id,
        )
        accelerator = request.requested_accelerator or "gpu"
        labels = {
            "platform.role": "compute",
            "platform.compute_enabled": "true",
            "platform.seller_user_id": request.seller_user_id,
            "platform.compute_node_id": compute_node_id,
            "platform.accelerator": accelerator,
        }
        expected_wireguard_ip = self._clean_optional_string(request.expected_wireguard_ip)
        return JoinMaterialResponse(
            join_token=join_token,
            manager_addr=manager_addr,
            manager_port=manager_port,
            registry_host=self.settings.registry_host,
            registry_port=self.settings.registry_port,
            swarm_join_command=f"docker swarm join --token {join_token} {manager_addr}:{manager_port}",
            claim_required=True,
            recommended_compute_node_id=compute_node_id,
            expected_wireguard_ip=expected_wireguard_ip,
            recommended_labels=labels,
            next_step="seller_host_runs_join_then_backend_calls_claim",
        )

    def claim_node(self, request: ClaimRequest) -> ClaimResponse:
        node_id = self._resolve_node_ref(request.node_ref)
        inspect = self.docker.node_inspect(node_id)
        hostname = inspect.get("Description", {}).get("Hostname", node_id)
        labels = inspect.get("Spec", {}).get("Labels", {}) or {}
        role = inspect.get("Spec", {}).get("Role", "")
        status = str(inspect.get("Status", {}).get("State", "")).lower()

        if self._is_control_plane(inspect):
            raise AdapterHTTPException(400, f"Refusing to claim control-plane/manager node {hostname}.", "node_claim_rejected")
        if role != "worker":
            raise AdapterHTTPException(400, f"Refusing to claim non-worker node {hostname} (role={role}).", "node_claim_rejected")
        if status != "ready":
            raise AdapterHTTPException(400, f"Refusing to claim node {hostname} because swarm status is {status}, not ready.", "node_claim_rejected")

        current_seller = labels.get("platform.seller_user_id")
        current_compute = labels.get("platform.compute_node_id")
        if current_seller and current_seller != request.seller_user_id:
            raise AdapterHTTPException(409, f"Refusing to change seller_user_id on claimed node {hostname}.", "node_claim_conflict")
        if current_compute and current_compute != request.compute_node_id:
            raise AdapterHTTPException(409, f"Refusing to change compute_node_id on claimed node {hostname}.", "node_claim_conflict")

        conflict = self._find_conflicting_compute_node_id(request.compute_node_id, exclude_node_id=node_id)
        if conflict is not None:
            raise AdapterHTTPException(
                409,
                f"Refusing duplicate compute_node_id={request.compute_node_id}; already present on {conflict.get('hostname')}.",
                "node_claim_conflict",
            )

        applied = {
            "platform.managed": "true",
            "platform.role": "compute",
            "platform.control_plane": "false",
            "platform.compute_enabled": "true",
            "platform.compute_node_id": request.compute_node_id,
            "platform.seller_user_id": request.seller_user_id,
            "platform.accelerator": request.accelerator,
        }
        updated = self.docker.node_update_labels(node_id, add_labels=applied)
        return ClaimResponse(
            status="claimed",
            node=self._node_summary_from_inspect(updated, running_tasks=self._running_tasks_for_node(node_id)),
            applied_labels=applied,
        )

    def set_availability(self, request: AvailabilityRequest) -> AvailabilityResponse:
        desired = request.availability.lower()
        if desired not in {"active", "drain"}:
            raise AdapterHTTPException(400, "Unsupported availability. Allowed values: active, drain.", "invalid_availability")

        node_id = self._resolve_node_ref(request.node_ref)
        inspect = self.docker.node_inspect(node_id)
        hostname = inspect.get("Description", {}).get("Hostname", node_id)
        role = inspect.get("Spec", {}).get("Role", "")
        status = str(inspect.get("Status", {}).get("State", "")).lower()
        current = str(inspect.get("Spec", {}).get("Availability", "")).lower()

        if self._is_control_plane(inspect):
            if current == desired:
                return AvailabilityResponse(
                    status="no_change",
                    node=self._node_summary_from_inspect(inspect, running_tasks=self._running_tasks_for_node(node_id)),
                )
            raise AdapterHTTPException(
                400,
                f"Refusing to mutate availability on control-plane/manager node {hostname}.",
                "availability_rejected",
            )

        if role != "worker":
            raise AdapterHTTPException(400, f"Refusing to mutate non-worker node {hostname} (role={role}).", "availability_rejected")

        if status != "ready" and current != desired:
            raise AdapterHTTPException(
                400,
                f"Refusing to mutate node {hostname} because swarm status is {status}, not ready.",
                "availability_rejected",
            )

        if current == desired:
            return AvailabilityResponse(
                status="no_change",
                node=self._node_summary_from_inspect(inspect, running_tasks=self._running_tasks_for_node(node_id)),
            )

        if desired == "drain":
            self._ensure_no_running_replicated_tasks(node_id)

        updated = self.docker.node_update_availability(node_id, desired)
        return AvailabilityResponse(
            status="updated",
            node=self._node_summary_from_inspect(updated, running_tasks=self._running_tasks_for_node(node_id)),
        )

    def remove_node(self, request: RemoveRequest) -> RemoveResponse:
        node_id = self._resolve_node_ref(request.node_ref)
        inspect = self.docker.node_inspect(node_id)
        hostname = inspect.get("Description", {}).get("Hostname", node_id)
        role = inspect.get("Spec", {}).get("Role", "")

        if self._is_control_plane(inspect):
            raise AdapterHTTPException(400, f"Refusing to remove control-plane/manager node {hostname}.", "node_remove_rejected")
        if role != "worker":
            raise AdapterHTTPException(400, f"Refusing to remove non-worker node {hostname} (role={role}).", "node_remove_rejected")

        availability = str(inspect.get("Spec", {}).get("Availability", "")).lower()
        if availability != "drain":
            self.set_availability(AvailabilityRequest(node_ref=node_id, availability="drain"))

        self._ensure_no_running_replicated_tasks(node_id)
        status = str(inspect.get("Status", {}).get("State", "")).lower()

        try:
            self.docker.node_update_labels(node_id, remove_labels=PLATFORM_LABEL_KEYS)
        except CommandExecutionError as exc:
            if not (request.force and status == "down"):
                raise AdapterHTTPException(409, exc.message, "node_remove_failed")

        removed_from_swarm = False
        detail: str | None = None
        latest_summary: NodeSummary | None = None

        if request.remove_from_swarm:
            latest = self.docker.node_inspect(node_id)
            latest_status = str(latest.get("Status", {}).get("State", "")).lower()
            try:
                self.docker.node_rm(node_id, force=False)
                removed_from_swarm = True
                detail = "node_removed_from_swarm"
            except CommandExecutionError as exc:
                if request.force and latest_status == "down":
                    self.docker.node_rm(node_id, force=True)
                    removed_from_swarm = True
                    detail = "node_removed_from_swarm_force"
                else:
                    raise AdapterHTTPException(409, exc.message, "node_remove_failed")
            if not removed_from_swarm:
                latest_summary = self._node_summary_from_inspect(latest, running_tasks=self._running_tasks_for_node(node_id))
        else:
            latest = self.docker.node_inspect(node_id)
            latest_summary = self._node_summary_from_inspect(latest, running_tasks=self._running_tasks_for_node(node_id))
            detail = "platform_labels_removed"

        return RemoveResponse(
            status="removed",
            removed_from_swarm=removed_from_swarm,
            labels_removed=PLATFORM_LABEL_KEYS,
            node=latest_summary,
            detail=detail,
        )

    def _swarm_info(self) -> dict[str, Any]:
        info = self.docker.info()
        state = str(info.get("LocalNodeState") or "").lower()
        if state != "active":
            raise AdapterHTTPException(503, "swarm_not_active", "swarm_not_active")
        return info

    def get_node_inspect(self, node_ref: str) -> dict[str, Any]:
        node_id = self._resolve_node_ref(node_ref)
        return self.docker.node_inspect(node_id)

    def get_node_inspect_by_compute_node_id(self, compute_node_id: str) -> dict[str, Any]:
        for row in self.docker.node_ls():
            inspect = self.docker.node_inspect(row["ID"])
            labels = inspect.get("Spec", {}).get("Labels", {}) or {}
            if labels.get("platform.compute_node_id") == compute_node_id:
                return inspect
        raise AdapterHTTPException(404, f"compute_node_id_not_found: {compute_node_id}", "node_not_found")

    def _list_node_summaries(self) -> list[NodeSummary]:
        summaries: list[NodeSummary] = []
        for row in self.docker.node_ls():
            inspect = self.docker.node_inspect(row["ID"])
            summaries.append(
                self._node_summary_from_inspect(
                    inspect,
                    running_tasks=self._running_tasks_for_node(row["ID"]),
                )
            )
        return summaries

    def _running_tasks_for_node(self, node_id: str) -> int:
        return self._running_task_count(self.docker.node_ps(node_id))

    @staticmethod
    def _running_task_count(tasks: list[dict[str, Any]]) -> int:
        return sum(1 for task in tasks if task.get("DesiredState") == "Running")

    @staticmethod
    def _is_truthy(value: str | None) -> bool:
        return str(value or "").lower() in {"true", "1", "yes"}

    def _is_control_plane(self, inspect: dict[str, Any]) -> bool:
        role = inspect.get("Spec", {}).get("Role", "")
        labels = inspect.get("Spec", {}).get("Labels", {}) or {}
        platform_role = labels.get("platform.role")
        control_plane = labels.get("platform.control_plane")
        return role == "manager" or platform_role == "control-plane" or self._is_truthy(control_plane)

    def _node_summary_from_inspect(self, inspect: dict[str, Any], running_tasks: int) -> NodeSummary:
        labels = inspect.get("Spec", {}).get("Labels", {}) or {}
        return NodeSummary(
            id=str(inspect.get("ID") or ""),
            hostname=str(inspect.get("Description", {}).get("Hostname") or ""),
            role=str(inspect.get("Spec", {}).get("Role") or ""),
            status=str(inspect.get("Status", {}).get("State") or "").lower(),
            availability=str(inspect.get("Spec", {}).get("Availability") or "").lower(),
            node_addr=str(inspect.get("Status", {}).get("Addr") or "") or None,
            platform_role=labels.get("platform.role"),
            compute_enabled=self._is_truthy(labels.get("platform.compute_enabled")),
            compute_node_id=labels.get("platform.compute_node_id"),
            seller_user_id=labels.get("platform.seller_user_id"),
            accelerator=labels.get("platform.accelerator"),
            running_tasks=running_tasks,
        )

    @staticmethod
    def _task_summary(task: dict[str, Any]) -> NodeTaskSummary:
        return NodeTaskSummary(
            id=task.get("ID"),
            name=str(task.get("Name") or ""),
            image=task.get("Image"),
            desired_state=str(task.get("DesiredState") or ""),
            current_state=str(task.get("CurrentState") or ""),
            error=task.get("Error") or None,
            ports=task.get("Ports") or None,
        )

    @staticmethod
    def _recent_error_summary(tasks: list[dict[str, Any]]) -> list[str]:
        summary: list[str] = []
        for task in tasks:
            if task.get("Error"):
                summary.append(str(task["Error"]))
            current_state = str(task.get("CurrentState") or "")
            if any(token in current_state.lower() for token in ("failed", "rejected", "shutdown")):
                summary.append(current_state)
        deduped: list[str] = []
        for item in summary:
            if item not in deduped:
                deduped.append(item)
        return deduped[:5]

    def _resolve_node_ref(self, node_ref: str) -> str:
        try:
            return self.docker.resolve_node_ref(node_ref)
        except CommandExecutionError as exc:
            raise AdapterHTTPException(404, exc.message, "node_not_found") from exc

    def _find_conflicting_compute_node_id(
        self,
        compute_node_id: str,
        exclude_node_id: str | None = None,
    ) -> dict[str, str] | None:
        for row in self.docker.node_ls():
            node_id = row.get("ID", "")
            if exclude_node_id and node_id == exclude_node_id:
                continue
            inspect = self.docker.node_inspect(node_id)
            labels = inspect.get("Spec", {}).get("Labels", {}) or {}
            if labels.get("platform.compute_node_id") == compute_node_id:
                return {
                    "id": node_id,
                    "hostname": inspect.get("Description", {}).get("Hostname", node_id),
                }
        return None

    def _recommended_compute_node_id(self, seller_user_id: str, requested: str | None) -> str:
        base = requested or f"compute-{self._slugify(seller_user_id)}"
        candidate = base
        suffix = 2
        while self._find_conflicting_compute_node_id(candidate) is not None:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def _clean_optional_string(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return slug or "node"

    def _ensure_no_running_replicated_tasks(self, node_id: str) -> None:
        tasks = self.docker.node_ps(node_id)
        hostname = self.docker.node_inspect(node_id).get("Description", {}).get("Hostname", node_id)
        for task in tasks:
            if task.get("DesiredState") != "Running":
                continue
            service_name = str(task.get("Name") or "").split(".")[0]
            if not service_name:
                continue
            service = self.docker.service_inspect(service_name)
            mode = service.get("Spec", {}).get("Mode", {})
            is_global = "Global" in mode
            if not is_global:
                raise AdapterHTTPException(
                    409,
                    f"Refusing to drain node {hostname}: running replicated task {task.get('Name')} ({task.get('CurrentState')}).",
                    "replicated_workload_present",
                )
