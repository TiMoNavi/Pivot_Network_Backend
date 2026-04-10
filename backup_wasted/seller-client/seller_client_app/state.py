from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from seller_client_app.backend import BackendClient
from seller_client_app.config import Settings
from seller_client_app.errors import LocalAppError


@dataclass
class SessionRuntimePaths:
    session_id: str
    session_root: Path
    codex_home: Path
    codex_dotdir: Path
    session_file: Path
    logs_dir: Path
    workspace_dir: Path


@dataclass
class JobRecord:
    job_id: str
    name: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


@dataclass
class WindowSessionRecord:
    session_id: str
    status: str
    opened_at: str
    last_heartbeat_at: str


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
        except Exception as exc:  # noqa: BLE001
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
        self._current_user: dict[str, Any] | None = None
        self._window_session: WindowSessionRecord | None = None
        self._onboarding_session: dict[str, Any] | None = None
        self._bootstrap_config: dict[str, Any] | None = None
        self._last_env_report: dict[str, Any] | None = None
        self._last_join_material: dict[str, Any] | None = None
        self._last_context_sync: dict[str, Any] | None = None
        self._last_standard_image_pull: dict[str, Any] | None = None
        self._last_standard_image_verify: dict[str, Any] | None = None
        self._last_wireguard_status: dict[str, Any] | None = None
        self._last_nodes: list[dict[str, Any]] = []
        self._last_build: dict[str, Any] | None = None
        self._active_processes: dict[str, Any] = {}
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def set_auth(self, token: str, user: dict[str, Any]) -> None:
        with self._lock:
            self._auth_token = token
            self._current_user = user

    def auth_token(self) -> str | None:
        with self._lock:
            return self._auth_token

    def current_user(self) -> dict[str, Any] | None:
        with self._lock:
            return self._current_user

    def open_window_session(self) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        record = WindowSessionRecord(
            session_id=str(uuid.uuid4()),
            status="active",
            opened_at=now,
            last_heartbeat_at=now,
        )
        with self._lock:
            self._window_session = record
        return self.current_window_session() or {}

    def current_window_session(self) -> dict[str, Any] | None:
        with self._lock:
            return self._serialize_window_session_locked()

    def heartbeat_window_session(self, session_id: str) -> dict[str, Any]:
        self.require_window_session(session_id)
        with self._lock:
            assert self._window_session is not None
            self._window_session.last_heartbeat_at = datetime.now(UTC).isoformat()
        return self.current_window_session() or {}

    def close_window_session(self, session_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            if self._window_session is None:
                return None
            if session_id and self._window_session.session_id != session_id:
                return None
            payload = {
                "session_id": self._window_session.session_id,
                "status": "closed",
                "opened_at": self._window_session.opened_at,
                "last_heartbeat_at": self._window_session.last_heartbeat_at,
            }
            self._window_session = None
        return payload

    def require_window_session(self, session_id: str | None) -> dict[str, Any]:
        record = self.current_window_session()
        if record is None:
            raise LocalAppError(
                step="window_session",
                code="window_session_missing",
                message="Browser window session is not initialized.",
                hint="Reload the seller console so it can create a new browser window session.",
                status_code=401,
            )
        if not session_id:
            raise LocalAppError(
                step="window_session",
                code="window_session_header_missing",
                message="Window session header is missing.",
                hint="Use the seller console browser window so requests carry the active window session id.",
                status_code=401,
            )
        if record["session_id"] != session_id:
            raise LocalAppError(
                step="window_session",
                code="window_session_mismatch",
                message="Window session does not match the current browser session.",
                hint="Refresh the seller console and retry within the current browser window.",
                status_code=409,
            )
        last_heartbeat = datetime.fromisoformat(record["last_heartbeat_at"])
        if datetime.now(UTC) - last_heartbeat > timedelta(seconds=self.settings.window_session_ttl_seconds):
            self.close_window_session(record["session_id"])
            raise LocalAppError(
                step="window_session",
                code="window_session_expired",
                message="Window session has expired.",
                hint="Reload the seller console to create a fresh browser-scoped Codex/MCP session.",
                status_code=401,
            )
        return record

    def current_onboarding_session(self) -> dict[str, Any] | None:
        with self._lock:
            return self._onboarding_session

    def current_bootstrap_config(self) -> dict[str, Any] | None:
        with self._lock:
            return self._bootstrap_config

    def last_join_material(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_join_material

    def last_context_sync(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_context_sync

    def last_standard_image_pull(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_standard_image_pull

    def last_standard_image_verify(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_standard_image_verify

    def last_wireguard_status(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_wireguard_status

    def last_build(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_build

    def set_onboarding(self, session_payload: dict[str, Any], bootstrap_config: dict[str, Any]) -> SessionRuntimePaths:
        paths = self.session_paths(session_payload["session_id"])
        paths.codex_dotdir.mkdir(parents=True, exist_ok=True)
        paths.logs_dir.mkdir(parents=True, exist_ok=True)
        paths.workspace_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._onboarding_session = session_payload
            self._bootstrap_config = bootstrap_config
        self.write_session_runtime_file()
        return paths

    def update_onboarding_session(self, session_payload: dict[str, Any]) -> None:
        with self._lock:
            self._onboarding_session = session_payload
        self.write_session_runtime_file()

    def set_last_env_report(self, env_report: dict[str, Any]) -> None:
        with self._lock:
            self._last_env_report = env_report
        self.write_session_runtime_file()

    def set_last_join_material(self, join_material: dict[str, Any]) -> None:
        with self._lock:
            self._last_join_material = join_material
        self.write_session_runtime_file()

    def set_last_context_sync(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_context_sync = payload
        self.write_session_runtime_file()

    def set_last_standard_image_pull(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_standard_image_pull = payload
        self.write_session_runtime_file()

    def set_last_standard_image_verify(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_standard_image_verify = payload
        self.write_session_runtime_file()

    def set_last_wireguard_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_wireguard_status = payload
        self.write_session_runtime_file()

    def set_last_nodes(self, nodes: list[dict[str, Any]]) -> None:
        with self._lock:
            self._last_nodes = nodes

    def set_last_build(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_build = payload
        self.write_session_runtime_file()

    def runtime_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "current_user": self._current_user,
                "window_session": self._serialize_window_session_locked(),
                "onboarding_session": self._onboarding_session,
                "bootstrap_config": self._bootstrap_config,
                "last_env_report": self._last_env_report,
                "last_join_material": self._last_join_material,
                "last_context_sync": self._last_context_sync,
                "last_standard_image_pull": self._last_standard_image_pull,
                "last_standard_image_verify": self._last_standard_image_verify,
                "last_wireguard_status": self._last_wireguard_status,
                "last_nodes": self._last_nodes,
                "last_build": self._last_build,
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
            logs_dir=session_root / "logs",
            workspace_dir=session_root / "workspace",
        )

    def write_session_runtime_file(self) -> Path | None:
        session = self.current_onboarding_session()
        if not session:
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
            "bootstrap_config": self.current_bootstrap_config(),
            "last_env_report": self._last_env_report,
            "last_join_material": self._last_join_material,
            "last_context_sync": self._last_context_sync,
            "last_standard_image_pull": self._last_standard_image_pull,
            "last_standard_image_verify": self._last_standard_image_verify,
            "last_wireguard_status": self._last_wireguard_status,
            "last_build": self._last_build,
            "workspace_root": str(self.settings.workspace_root_path),
        }
        paths.session_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return paths.session_file

    def register_process(self, session_id: str, process: Any) -> None:
        with self._lock:
            self._active_processes[session_id] = process

    def stop_registered_process(self, session_id: str) -> None:
        with self._lock:
            process = self._active_processes.pop(session_id, None)
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                return

    def start_heartbeat(self, backend_client: BackendClient, session_id: str) -> None:
        self.stop_heartbeat()
        self._heartbeat_stop.clear()

        def _run() -> None:
            while not self._heartbeat_stop.wait(self.settings.heartbeat_interval_seconds):
                try:
                    payload = backend_client.heartbeat_onboarding_session(session_id)
                except Exception:
                    continue
                self.update_onboarding_session(payload)

        self._heartbeat_thread = threading.Thread(target=_run, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)
        self._heartbeat_thread = None

    def cleanup_session(self, session_id: str) -> None:
        self.stop_registered_process(session_id)
        self.stop_heartbeat()
        paths = self.session_paths(session_id)
        config_path = paths.codex_dotdir / "config.toml"
        auth_path = paths.codex_dotdir / "auth.json"
        for file_path in (config_path, auth_path):
            if file_path.exists():
                file_path.unlink()
        with self._lock:
            self._onboarding_session = None
            self._bootstrap_config = None
            self._last_env_report = None
            self._last_join_material = None
            self._last_context_sync = None
            self._last_standard_image_pull = None
            self._last_standard_image_verify = None
            self._last_wireguard_status = None
            self._last_build = None
        self.write_cleanup_marker(paths)

    def write_cleanup_marker(self, paths: SessionRuntimePaths) -> None:
        paths.session_root.mkdir(parents=True, exist_ok=True)
        marker_path = paths.session_root / "cleanup.json"
        marker_path.write_text(
            json.dumps({"cleaned_at": datetime.now(UTC).isoformat()}, indent=2),
            encoding="utf-8",
        )

    def _serialize_window_session_locked(self) -> dict[str, Any] | None:
        if self._window_session is None:
            return None
        return {
            "session_id": self._window_session.session_id,
            "status": self._window_session.status,
            "opened_at": self._window_session.opened_at,
            "last_heartbeat_at": self._window_session.last_heartbeat_at,
            "ttl_seconds": self.settings.window_session_ttl_seconds,
        }
