from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend_app.clients.adapter.client import AdapterClient, AdapterClientError
from backend_app.core.config import get_settings
from backend_app.db.models.audit import OperationLog
from backend_app.db.models.swarm import (
    SwarmCluster,
    SwarmNode,
    SwarmNodeLabel,
    SwarmService,
    SwarmSyncEvent,
    SwarmSyncRun,
    SwarmTask,
)
from backend_app.schemas.platform import SwarmSyncResponse
from backend_app.services.audit_service import AuditService


class SwarmSyncService:
    def __init__(self, session: Session, adapter_client: AdapterClient) -> None:
        self.session = session
        self.adapter_client = adapter_client
        self.settings = get_settings()
        self.audit = AuditService(session)

    def sync(self, sync_scope: str = "manual") -> SwarmSyncResponse:
        run = SwarmSyncRun(
            sync_scope=sync_scope,
            started_at=datetime.now(UTC),
            status="running",
            nodes_changed=0,
            services_changed=0,
            tasks_changed=0,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        try:
            overview = self.adapter_client.get_swarm_overview()
            cluster = self._upsert_cluster(overview)
            nodes_changed = self._sync_nodes(run.id, cluster.id, overview)
            services_changed, tasks_changed = self._sync_services(run.id, cluster.id, overview)

            cluster.last_synced_at = datetime.now(UTC)
            cluster.status = "ok"
            run.finished_at = datetime.now(UTC)
            run.status = "success"
            run.nodes_changed = nodes_changed
            run.services_changed = services_changed
            run.tasks_changed = tasks_changed
            self.audit.log_operation(
                operation_type="swarm_sync",
                target_type="swarm_cluster",
                target_key=str(cluster.cluster_key),
                request_payload={"sync_scope": sync_scope},
                response_payload=overview,
                status="success",
            )
            self.session.commit()
        except AdapterClientError as exc:
            run.finished_at = datetime.now(UTC)
            run.status = "failed"
            run.error_summary = exc.detail
            self.audit.log_operation(
                operation_type="swarm_sync",
                target_type="swarm_cluster",
                target_key="primary",
                request_payload={"sync_scope": sync_scope},
                response_payload=exc.payload,
                status="failed",
                error_message=exc.detail,
            )
            self.session.commit()
            return SwarmSyncResponse(
                sync_run_id=str(run.id),
                sync_scope=sync_scope,
                status="failed",
                nodes_changed=run.nodes_changed,
                services_changed=run.services_changed,
                tasks_changed=run.tasks_changed,
                error_summary=run.error_summary,
            )

        return SwarmSyncResponse(
            sync_run_id=str(run.id),
            sync_scope=sync_scope,
            status=run.status,
            nodes_changed=run.nodes_changed,
            services_changed=run.services_changed,
            tasks_changed=run.tasks_changed,
            error_summary=run.error_summary,
        )

    def _upsert_cluster(self, overview: dict[str, Any]) -> SwarmCluster:
        cluster = self.session.scalar(select(SwarmCluster).where(SwarmCluster.cluster_key == "primary"))
        if cluster is None:
            cluster = SwarmCluster(
                cluster_key="primary",
                adapter_base_url=self.settings.adapter_base_url,
                manager_host=overview.get("manager_host") or self.settings.adapter_base_url,
                status="ok",
                last_synced_at=datetime.now(UTC),
            )
            self.session.add(cluster)
            self.session.flush()
            self._record_sync_event(
                None,
                "swarm_cluster",
                "primary",
                "created",
                None,
                {"manager_host": cluster.manager_host},
            )
            return cluster

        before = {"manager_host": cluster.manager_host, "status": cluster.status}
        cluster.adapter_base_url = self.settings.adapter_base_url
        cluster.manager_host = overview.get("manager_host") or cluster.manager_host
        cluster.status = "ok"
        cluster.last_synced_at = datetime.now(UTC)
        after = {"manager_host": cluster.manager_host, "status": cluster.status}
        if before != after:
            self._record_sync_event(None, "swarm_cluster", "primary", "updated", before, after)
        self.session.flush()
        return cluster

    def _sync_nodes(self, sync_run_id, cluster_id, overview: dict[str, Any]) -> int:
        live_nodes = self.adapter_client.list_nodes().get("nodes", [])
        changed = 0

        existing_nodes = {
            node.swarm_node_id: node
            for node in self.session.scalars(select(SwarmNode).where(SwarmNode.cluster_id == cluster_id))
        }
        seen_ids: set[str] = set()

        for node_summary in live_nodes:
            node_id = node_summary["id"]
            seen_ids.add(node_id)
            inspect_payload = self.adapter_client.inspect_node({"node_ref": node_id})
            node = inspect_payload["node"]
            raw_payload = inspect_payload

            existing = existing_nodes.get(node_id)
            before = None
            if existing is None:
                existing = SwarmNode(
                    cluster_id=cluster_id,
                    swarm_node_id=node_id,
                    hostname=node["hostname"],
                    role=node["role"],
                    status=node["status"],
                    availability=node["availability"],
                    platform_role=node.get("platform_role"),
                    compute_enabled=bool(node.get("compute_enabled")),
                    compute_node_id=node.get("compute_node_id"),
                    seller_user_id=node.get("seller_user_id"),
                    accelerator=node.get("accelerator"),
                    last_seen_at=datetime.now(UTC),
                    raw_payload=raw_payload,
                )
                self.session.add(existing)
                self.session.flush()
                changed += 1
                self._record_sync_event(
                    sync_run_id,
                    "swarm_node",
                    node_id,
                    "created",
                    None,
                    raw_payload,
                )
            else:
                before = existing.raw_payload
                existing.hostname = node["hostname"]
                existing.role = node["role"]
                existing.status = node["status"]
                existing.availability = node["availability"]
                existing.platform_role = node.get("platform_role")
                existing.compute_enabled = bool(node.get("compute_enabled"))
                existing.compute_node_id = node.get("compute_node_id")
                existing.seller_user_id = node.get("seller_user_id")
                existing.accelerator = node.get("accelerator")
                existing.last_seen_at = datetime.now(UTC)
                existing.raw_payload = raw_payload
                self.session.flush()
                if before != raw_payload:
                    changed += 1
                    self._record_sync_event(sync_run_id, "swarm_node", node_id, "updated", before, raw_payload)

            self.session.execute(delete(SwarmNodeLabel).where(SwarmNodeLabel.node_id == existing.id))
            labels = inspect_payload.get("raw_labels", {})
            for key, value in labels.items():
                self.session.add(SwarmNodeLabel(node_id=existing.id, label_key=key, label_value=str(value)))

        for node_id, node in existing_nodes.items():
            if node_id in seen_ids:
                continue
            self._record_sync_event(sync_run_id, "swarm_node", node_id, "deleted", node.raw_payload, None)
            self.session.execute(delete(SwarmNodeLabel).where(SwarmNodeLabel.node_id == node.id))
            self.session.delete(node)
            changed += 1

        self.session.flush()
        return changed

    def _sync_services(self, sync_run_id, cluster_id, overview: dict[str, Any]) -> tuple[int, int]:
        services_summary = overview.get("service_list_summary", [])
        changed_services = 0
        changed_tasks = 0

        node_by_hostname = {
            node.hostname: node
            for node in self.session.scalars(select(SwarmNode).where(SwarmNode.cluster_id == cluster_id))
        }
        existing_services = {
            service.swarm_service_id: service
            for service in self.session.scalars(select(SwarmService).where(SwarmService.cluster_id == cluster_id))
        }
        seen_service_ids: set[str] = set()

        for summary in services_summary:
            service_name = summary["name"]
            inspect_payload = self.adapter_client.inspect_service({"service_name": service_name})
            service_id = inspect_payload["service_id"]
            seen_service_ids.add(service_id)
            desired_replicas, running_replicas = self._parse_replicas(summary.get("replicas"))

            existing = existing_services.get(service_id)
            before = None
            if existing is None:
                existing = SwarmService(
                    cluster_id=cluster_id,
                    swarm_service_id=service_id,
                    service_name=inspect_payload["service_name"],
                    service_kind=self._service_kind(inspect_payload["service_name"]),
                    mode=inspect_payload["mode"],
                    image=inspect_payload["image"],
                    desired_replicas=desired_replicas,
                    running_replicas=running_replicas,
                    status=inspect_payload["status"],
                    last_synced_at=datetime.now(UTC),
                    raw_payload=inspect_payload,
                )
                self.session.add(existing)
                self.session.flush()
                changed_services += 1
                self._record_sync_event(sync_run_id, "swarm_service", service_id, "created", None, inspect_payload)
            else:
                before = existing.raw_payload
                existing.service_name = inspect_payload["service_name"]
                existing.service_kind = self._service_kind(inspect_payload["service_name"])
                existing.mode = inspect_payload["mode"]
                existing.image = inspect_payload["image"]
                existing.desired_replicas = desired_replicas
                existing.running_replicas = running_replicas
                existing.status = inspect_payload["status"]
                existing.last_synced_at = datetime.now(UTC)
                existing.raw_payload = inspect_payload
                self.session.flush()
                if before != inspect_payload:
                    changed_services += 1
                    self._record_sync_event(sync_run_id, "swarm_service", service_id, "updated", before, inspect_payload)

            self.session.execute(delete(SwarmTask).where(SwarmTask.service_id == existing.id))
            for task in inspect_payload.get("tasks", []):
                mapped_node = node_by_hostname.get(task.get("node") or "")
                self.session.add(
                    SwarmTask(
                        service_id=existing.id,
                        swarm_task_id=task.get("id") or f"{service_id}:{task.get('name')}",
                        node_id=mapped_node.id if mapped_node else None,
                        desired_state=task.get("desired_state") or "",
                        current_state=task.get("current_state") or "",
                        error_message=task.get("error"),
                        container_id=task.get("container_id"),
                        last_synced_at=datetime.now(UTC),
                        raw_payload=task,
                    )
                )
                changed_tasks += 1

        for service_id, service in existing_services.items():
            if service_id in seen_service_ids:
                continue
            self._record_sync_event(sync_run_id, "swarm_service", service_id, "deleted", service.raw_payload, None)
            self.session.execute(delete(SwarmTask).where(SwarmTask.service_id == service.id))
            self.session.delete(service)
            changed_services += 1

        self.session.flush()
        return changed_services, changed_tasks

    def _record_sync_event(
        self,
        sync_run_id,
        entity_type: str,
        entity_key: str,
        change_type: str,
        before_payload: dict[str, Any] | None,
        after_payload: dict[str, Any] | None,
    ) -> None:
        if sync_run_id is None:
            return
        self.session.add(
            SwarmSyncEvent(
                sync_run_id=sync_run_id,
                entity_type=entity_type,
                entity_key=entity_key,
                change_type=change_type,
                before_payload=before_payload,
                after_payload=after_payload,
                created_at=datetime.now(UTC),
            )
        )
        self.session.flush()

    @staticmethod
    def _parse_replicas(replicas: str | None) -> tuple[int | None, int | None]:
        if not replicas or "/" not in replicas:
            return None, None
        running, desired = replicas.split("/", 1)
        try:
            return int(desired), int(running)
        except ValueError:
            return None, None

    @staticmethod
    def _service_kind(service_name: str) -> str:
        if service_name.startswith("runtime-"):
            return "runtime"
        if service_name.startswith("gateway-"):
            return "gateway"
        return "other"
