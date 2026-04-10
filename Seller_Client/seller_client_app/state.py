from __future__ import annotations

import json
import socket
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from seller_client_app.config import Settings
from seller_client_app.errors import LocalAppError

DEFAULT_TCP_TIMEOUT_MS = 3000
_UNSET = object()


def empty_runtime_evidence() -> dict[str, Any]:
    return {
        "correction_history": [],
        "latest_correction": None,
        "tcp_validations": [],
        "latest_tcp_validation": None,
        "updated_at": None,
    }


def normalize_runtime_evidence(payload: dict[str, Any] | None) -> dict[str, Any]:
    evidence = empty_runtime_evidence()
    if not isinstance(payload, dict):
        return evidence

    correction_history = payload.get("correction_history")
    if isinstance(correction_history, list):
        evidence["correction_history"] = [dict(item) for item in correction_history if isinstance(item, dict)]

    tcp_validations = payload.get("tcp_validations")
    if isinstance(tcp_validations, list):
        evidence["tcp_validations"] = [dict(item) for item in tcp_validations if isinstance(item, dict)]

    latest_correction = payload.get("latest_correction")
    if isinstance(latest_correction, dict):
        evidence["latest_correction"] = dict(latest_correction)
    elif evidence["correction_history"]:
        evidence["latest_correction"] = dict(evidence["correction_history"][-1])

    latest_tcp_validation = payload.get("latest_tcp_validation")
    if isinstance(latest_tcp_validation, dict):
        evidence["latest_tcp_validation"] = dict(latest_tcp_validation)
    elif evidence["tcp_validations"]:
        evidence["latest_tcp_validation"] = dict(evidence["tcp_validations"][-1])

    updated_at = payload.get("updated_at")
    if isinstance(updated_at, str) and updated_at.strip():
        evidence["updated_at"] = updated_at.strip()
    return evidence


def append_correction_evidence(
    runtime_evidence: dict[str, Any] | None,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = normalize_runtime_evidence(runtime_evidence)
    recorded_at = datetime.now(UTC).isoformat()
    record = _compact(
        {
            "correction_kind": _required_string(payload, "correction_kind"),
            "outcome": _required_string(payload, "outcome"),
            "reported_phase": _optional_string(payload.get("reported_phase")),
            "join_mode": _optional_string(payload.get("join_mode")),
            "target_host": _optional_string(payload.get("target_host")),
            "target_port": _optional_port(payload.get("target_port")),
            "observed_wireguard_ip": _optional_string(payload.get("observed_wireguard_ip")),
            "observed_advertise_addr": _optional_string(payload.get("observed_advertise_addr")),
            "observed_data_path_addr": _optional_string(payload.get("observed_data_path_addr")),
            "manager_node_addr_hint": _optional_string(payload.get("manager_node_addr_hint")),
            "script_path": _optional_string(payload.get("script_path")),
            "log_path": _optional_string(payload.get("log_path")),
            "rollback_path": _optional_string(payload.get("rollback_path")),
            "notes": list(payload.get("notes") or []),
            "raw_payload": dict(payload.get("raw_payload") or {}),
            "recorded_at": recorded_at,
        }
    )
    evidence["correction_history"].append(record)
    evidence["latest_correction"] = record
    evidence["updated_at"] = recorded_at
    return evidence, record


def run_minimum_tcp_validation(
    runtime_evidence: dict[str, Any] | None,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = normalize_runtime_evidence(runtime_evidence)
    host = _required_string(payload, "host")
    port = _required_port(payload, "port")
    timeout_ms = _bounded_timeout_ms(payload.get("timeout_ms"))
    validated_at = datetime.now(UTC).isoformat()
    error: str | None = None
    reachable = False

    try:
        with socket.create_connection((host, port), timeout=timeout_ms / 1000):
            reachable = True
    except OSError as exc:
        error = str(exc)

    record = _compact(
        {
            "validation_kind": _optional_string(payload.get("validation_kind")) or "minimum_tcp_connect",
            "source": _optional_string(payload.get("source")) or "seller_client_local",
            "target_label": _optional_string(payload.get("target_label")),
            "host": host,
            "port": port,
            "timeout_ms": timeout_ms,
            "reachable": reachable,
            "error": error,
            "notes": list(payload.get("notes") or []),
            "raw_payload": dict(payload.get("raw_payload") or {}),
            "validated_at": validated_at,
        }
    )
    evidence["tcp_validations"].append(record)
    evidence["latest_tcp_validation"] = record
    evidence["updated_at"] = validated_at
    return evidence, record


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = _optional_string(payload.get(key))
    if value is None:
        raise ValueError(f"{key} is required.")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_port(value: Any) -> int | None:
    if value is None:
        return None
    port = int(value)
    if port < 1 or port > 65535:
        raise ValueError("port must be between 1 and 65535.")
    return port


def _required_port(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"{key} is required.")
    port = _optional_port(value)
    if port is None:
        raise ValueError(f"{key} is required.")
    return port


def _bounded_timeout_ms(value: Any) -> int:
    if value is None:
        return DEFAULT_TCP_TIMEOUT_MS
    timeout_ms = int(value)
    if timeout_ms < 1 or timeout_ms > 60000:
        raise ValueError("timeout_ms must be between 1 and 60000.")
    return timeout_ms


@dataclass(slots=True)
class SessionRuntimePaths:
    session_id: str
    session_root: Path
    codex_home: Path
    codex_dotdir: Path
    session_file: Path
    logs_dir: Path
    workspace_dir: Path


@dataclass(slots=True)
class WindowSessionRecord:
    session_id: str
    status: str
    opened_at: str
    last_heartbeat_at: str

    def to_dict(self, ttl_seconds: int) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "opened_at": self.opened_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "ttl_seconds": ttl_seconds,
        }


@dataclass(slots=True)
class JobRecord:
    job_id: str
    name: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, task: Callable[[], dict[str, Any]]) -> JobRecord:
        job = JobRecord(
            job_id=str(uuid.uuid4()),
            name=name,
            status="queued",
            created_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._jobs[job.job_id] = job

        thread = threading.Thread(target=self._run_job, args=(job.job_id, task), daemon=True)
        thread.start()
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run_job(self, job_id: str, task: Callable[[], dict[str, Any]]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = datetime.now(UTC).isoformat()
        try:
            result = task()
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                if isinstance(exc, LocalAppError):
                    job.error = exc.to_dict()["error"]
                else:
                    job.error = {
                        "step": job.name,
                        "code": "job_failed",
                        "message": str(exc),
                        "hint": None,
                        "details": {},
                    }
                job.finished_at = datetime.now(UTC).isoformat()
            return

        with self._lock:
            job = self._jobs[job_id]
            job.status = "succeeded"
            job.result = result
            job.finished_at = datetime.now(UTC).isoformat()


class SellerClientState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jobs = JobManager()
        self._lock = threading.Lock()
        self._auth_token: str | None = None
        self._auth_expires_at: str | None = None
        self._current_user: dict[str, Any] | None = None
        self._window_session: WindowSessionRecord | None = None
        self._onboarding_session: dict[str, Any] | None = None
        self._runtime_evidence: dict[str, Any] | None = None
        self._local_health_snapshot: dict[str, Any] | None = None
        self._last_runtime_workflow: dict[str, Any] | None = None
        self._last_assistant_run: dict[str, Any] | None = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def set_auth(self, token: str, user: dict[str, Any], expires_at: str | None) -> None:
        with self._lock:
            self._auth_token = token
            self._current_user = user
            self._auth_expires_at = expires_at
        self.write_session_runtime_file()

    def auth_token(self) -> str | None:
        with self._lock:
            return self._auth_token

    def auth_session(self) -> dict[str, Any] | None:
        with self._lock:
            if self._auth_token is None:
                return None
            return {
                "expires_at": self._auth_expires_at,
                "user_id": None if self._current_user is None else self._current_user.get("id"),
            }

    def current_user(self) -> dict[str, Any] | None:
        with self._lock:
            return self._current_user

    def update_current_user(self, user: dict[str, Any]) -> None:
        with self._lock:
            self._current_user = user
        self.write_session_runtime_file()

    def open_window_session(self) -> dict[str, Any]:
        current = self.current_window_session()
        if current is not None:
            last_heartbeat = datetime.fromisoformat(current["last_heartbeat_at"])
            if datetime.now(UTC) - last_heartbeat <= timedelta(seconds=self.settings.window_session_ttl_seconds):
                return current
            self.close_window_session(current["session_id"])

        now = datetime.now(UTC).isoformat()
        record = WindowSessionRecord(
            session_id=str(uuid.uuid4()),
            status="active",
            opened_at=now,
            last_heartbeat_at=now,
        )
        with self._lock:
            self._window_session = record
        self.write_session_runtime_file()
        return self.current_window_session() or {}

    def current_window_session(self) -> dict[str, Any] | None:
        with self._lock:
            return self._serialize_window_session_locked()

    def require_window_session(self, session_id: str | None) -> dict[str, Any]:
        record = self.current_window_session()
        if record is None:
            raise LocalAppError(
                step="window_session",
                code="window_session_missing",
                message="Browser window session is not initialized.",
                hint="Reload the seller client page to create a browser-scoped session.",
                status_code=401,
            )
        if not session_id:
            raise LocalAppError(
                step="window_session",
                code="window_session_header_missing",
                message="Window session header is missing.",
                hint="Use the seller client browser page so requests include the active window session id.",
                status_code=401,
            )
        if record["session_id"] != session_id:
            raise LocalAppError(
                step="window_session",
                code="window_session_mismatch",
                message="Window session does not match the current browser session.",
                hint="Refresh the page and retry within the current browser window.",
                status_code=409,
            )
        last_heartbeat = datetime.fromisoformat(record["last_heartbeat_at"])
        if datetime.now(UTC) - last_heartbeat > timedelta(seconds=self.settings.window_session_ttl_seconds):
            self.close_window_session(record["session_id"])
            raise LocalAppError(
                step="window_session",
                code="window_session_expired",
                message="Window session has expired.",
                hint="Reload the seller client page to create a fresh browser session.",
                status_code=401,
            )
        return record

    def heartbeat_window_session(self, session_id: str) -> dict[str, Any]:
        self.require_window_session(session_id)
        with self._lock:
            assert self._window_session is not None
            self._window_session.last_heartbeat_at = datetime.now(UTC).isoformat()
        self.write_session_runtime_file()
        return self.current_window_session() or {}

    def close_window_session(self, session_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            if self._window_session is None:
                return None
            if session_id and self._window_session.session_id != session_id:
                return None
            closed = self._window_session.to_dict(self.settings.window_session_ttl_seconds)
            closed["status"] = "closed"
            self._window_session = None
        self.write_session_runtime_file()
        return closed

    def current_onboarding_session(self) -> dict[str, Any] | None:
        with self._lock:
            return self._onboarding_session

    def current_runtime_evidence(self) -> dict[str, Any]:
        with self._lock:
            return normalize_runtime_evidence(self._runtime_evidence)

    def current_local_health_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._local_health_snapshot is None else dict(self._local_health_snapshot)

    def current_last_runtime_workflow(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._last_runtime_workflow is None else dict(self._last_runtime_workflow)

    def refresh_from_session_file(self, session_id: str) -> dict[str, Any] | None:
        session_file = self.session_paths(session_id).session_file
        if not session_file.exists():
            return None
        payload = json.loads(session_file.read_text(encoding="utf-8"))
        window_session = _deserialize_window_session(payload.get("window_session"))
        with self._lock:
            auth_token = payload.get("auth_token")
            if isinstance(auth_token, str) and auth_token.strip():
                self._auth_token = auth_token
            current_user = payload.get("current_user")
            if isinstance(current_user, dict):
                self._current_user = dict(current_user)
            self._window_session = window_session
            onboarding = payload.get("onboarding_session")
            self._onboarding_session = dict(onboarding) if isinstance(onboarding, dict) else None
            self._runtime_evidence = normalize_runtime_evidence(payload.get("runtime_evidence"))
            local_health_snapshot = payload.get("local_health_snapshot")
            self._local_health_snapshot = (
                dict(local_health_snapshot) if isinstance(local_health_snapshot, dict) else None
            )
            runtime_workflow = payload.get("last_runtime_workflow")
            self._last_runtime_workflow = dict(runtime_workflow) if isinstance(runtime_workflow, dict) else None
            assistant_run = payload.get("last_assistant_run")
            self._last_assistant_run = dict(assistant_run) if isinstance(assistant_run, dict) else None
        return self.runtime_snapshot()

    def set_onboarding(self, session_payload: dict[str, Any]) -> SessionRuntimePaths:
        session_id = session_payload["session_id"]
        current_evidence = self.current_runtime_evidence()
        current_session = self.current_onboarding_session()
        runtime_evidence = (
            current_evidence
            if current_session is not None and current_session.get("session_id") == session_id
            else self._load_runtime_evidence(session_id)
        )
        local_health_snapshot = (
            self.current_local_health_snapshot()
            if current_session is not None and current_session.get("session_id") == session_id
            else self._load_persisted_payload(session_id, "local_health_snapshot")
        )
        last_runtime_workflow = (
            self.current_last_runtime_workflow()
            if current_session is not None and current_session.get("session_id") == session_id
            else self._load_persisted_payload(session_id, "last_runtime_workflow")
        )
        with self._lock:
            self._onboarding_session = session_payload
            self._runtime_evidence = runtime_evidence
            self._local_health_snapshot = local_health_snapshot
            self._last_runtime_workflow = last_runtime_workflow
        self.write_session_runtime_file()
        return self.session_paths(session_id)

    def update_onboarding_session(self, session_payload: dict[str, Any]) -> None:
        with self._lock:
            self._onboarding_session = session_payload
            self._runtime_evidence = normalize_runtime_evidence(self._runtime_evidence)
        self.write_session_runtime_file()

    def record_local_health_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._local_health_snapshot = dict(payload)
        self.write_session_runtime_file()
        return payload

    def record_runtime_workflow_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._last_runtime_workflow = dict(payload)
        self.write_session_runtime_file()
        return payload

    def record_correction_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._runtime_evidence, record = append_correction_evidence(self._runtime_evidence, payload)
            runtime_evidence = normalize_runtime_evidence(self._runtime_evidence)
        self.write_session_runtime_file()
        return {"correction": record, "runtime_evidence": runtime_evidence}

    def record_tcp_validation(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._runtime_evidence, record = run_minimum_tcp_validation(self._runtime_evidence, payload)
            runtime_evidence = normalize_runtime_evidence(self._runtime_evidence)
        self.write_session_runtime_file()
        return {"validation": record, "runtime_evidence": runtime_evidence}

    def record_assistant_run(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_assistant_run = payload
        self.write_session_runtime_file()

    def reset_join_state(
        self,
        *,
        runtime_workflow: dict[str, Any] | None = None,
        local_health_snapshot: dict[str, Any] | None | object = _UNSET,
        clear_runtime_evidence: bool = True,
        clear_last_assistant_run: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            self._runtime_evidence = empty_runtime_evidence() if clear_runtime_evidence else normalize_runtime_evidence(
                self._runtime_evidence
            )
            self._last_runtime_workflow = None if runtime_workflow is None else dict(runtime_workflow)
            if clear_last_assistant_run:
                self._last_assistant_run = None
            if local_health_snapshot is not _UNSET:
                self._local_health_snapshot = None if local_health_snapshot is None else dict(local_health_snapshot)
        self.write_session_runtime_file()
        return self.runtime_snapshot()

    def runtime_snapshot(self) -> dict[str, Any]:
        with self._lock:
            onboarding = self._onboarding_session
            paths = None
            if onboarding is not None:
                session_paths = self.session_paths(onboarding["session_id"])
                paths = {
                    "session_root": str(session_paths.session_root),
                    "session_file": str(session_paths.session_file),
                    "logs_dir": str(session_paths.logs_dir),
                    "workspace_dir": str(session_paths.workspace_dir),
                }
            return {
                "current_user": self._current_user,
                "auth_session": None
                if self._auth_token is None
                else {"expires_at": self._auth_expires_at},
                "window_session": self._serialize_window_session_locked(),
                "onboarding_session": onboarding,
                "runtime_evidence": normalize_runtime_evidence(self._runtime_evidence),
                "local_health_snapshot": None if self._local_health_snapshot is None else dict(self._local_health_snapshot),
                "last_runtime_workflow": None if self._last_runtime_workflow is None else dict(self._last_runtime_workflow),
                "last_assistant_run": self._last_assistant_run,
                "paths": paths,
            }

    def session_paths(self, session_id: str) -> SessionRuntimePaths:
        session_root = self.settings.workspace_root_path / self.settings.session_subdir_name / session_id
        codex_home = session_root / "codex-home"
        return SessionRuntimePaths(
            session_id=session_id,
            session_root=session_root,
            codex_home=codex_home,
            codex_dotdir=codex_home / ".codex",
            session_file=session_root / "session.json",
            logs_dir=session_root / self.settings.logs_subdir_name,
            workspace_dir=session_root / self.settings.workspace_subdir_name,
        )

    def write_session_runtime_file(self) -> Path | None:
        session = self.current_onboarding_session()
        if session is None:
            return None
        paths = self.session_paths(session["session_id"])
        paths.session_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "backend_base_url": self.settings.backend_base_url,
            "backend_api_prefix": self.settings.backend_api_prefix,
            "auth_token": self.auth_token(),
            "current_user": self.current_user(),
            "window_session": self.current_window_session(),
            "onboarding_session": session,
            "runtime_evidence": self.current_runtime_evidence(),
            "local_health_snapshot": self.current_local_health_snapshot(),
            "last_runtime_workflow": self.current_last_runtime_workflow(),
            "last_assistant_run": self._last_assistant_run,
            "workspace_root": str(self.settings.workspace_root_path),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _atomic_write_text(paths.session_file, json.dumps(payload, ensure_ascii=False, indent=2))
        return paths.session_file

    def start_heartbeat(self, task: Callable[[], dict[str, Any]]) -> None:
        self.stop_heartbeat()
        self._heartbeat_stop.clear()

        def _run() -> None:
            while not self._heartbeat_stop.wait(self.settings.heartbeat_interval_seconds):
                try:
                    task()
                except Exception:
                    continue

        self._heartbeat_thread = threading.Thread(target=_run, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)
        self._heartbeat_thread = None

    def cleanup_session(self, session_id: str) -> None:
        self.stop_heartbeat()
        paths = self.session_paths(session_id)
        for path in (paths.codex_dotdir / "config.toml", paths.codex_dotdir / "auth.json"):
            if path.exists():
                path.unlink()
        with self._lock:
            self._onboarding_session = None
            self._runtime_evidence = None
            self._local_health_snapshot = None
            self._last_runtime_workflow = None
            self._last_assistant_run = None
        self.write_cleanup_marker(paths)

    def write_cleanup_marker(self, paths: SessionRuntimePaths) -> None:
        paths.session_root.mkdir(parents=True, exist_ok=True)
        cleanup_path = paths.session_root / "cleanup.json"
        cleanup_path.write_text(
            json.dumps({"cleaned_at": datetime.now(UTC).isoformat()}, indent=2),
            encoding="utf-8",
        )

    def reset_for_tests(self) -> None:
        self.stop_heartbeat()
        with self._lock:
            self._auth_token = None
            self._auth_expires_at = None
            self._current_user = None
            self._window_session = None
            self._onboarding_session = None
            self._runtime_evidence = None
            self._local_health_snapshot = None
            self._last_runtime_workflow = None
            self._last_assistant_run = None

    def _serialize_window_session_locked(self) -> dict[str, Any] | None:
        if self._window_session is None:
            return None
        return self._window_session.to_dict(self.settings.window_session_ttl_seconds)

    def _load_runtime_evidence(self, session_id: str) -> dict[str, Any]:
        session_file = self.session_paths(session_id).session_file
        if not session_file.exists():
            return empty_runtime_evidence()
        try:
            payload = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return empty_runtime_evidence()
        return normalize_runtime_evidence(payload.get("runtime_evidence"))

    def _load_persisted_payload(self, session_id: str, key: str) -> dict[str, Any] | None:
        session_file = self.session_paths(session_id).session_file
        if not session_file.exists():
            return None
        try:
            payload = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        persisted = payload.get(key)
        if not isinstance(persisted, dict):
            return None
        return dict(persisted)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def _deserialize_window_session(payload: Any) -> WindowSessionRecord | None:
    if not isinstance(payload, dict):
        return None
    if str(payload.get("status") or "active").strip().lower() != "active":
        return None
    session_id = str(payload.get("session_id") or "").strip()
    opened_at = str(payload.get("opened_at") or "").strip()
    last_heartbeat_at = str(payload.get("last_heartbeat_at") or "").strip()
    if not session_id or not opened_at or not last_heartbeat_at:
        return None
    return WindowSessionRecord(
        session_id=session_id,
        status="active",
        opened_at=opened_at,
        last_heartbeat_at=last_heartbeat_at,
    )
