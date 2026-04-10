from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from buyer_client_app.backend import BackendClient
from buyer_client_app.config import Settings
from buyer_client_app.errors import LocalAppError


@dataclass
class SessionRuntimePaths:
    session_id: str
    session_root: Path
    codex_home: Path
    codex_dotdir: Path
    session_file: Path
    logs_dir: Path
    workspace_dir: Path
    wireguard_dir: Path


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


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, task: Callable[[], dict[str, Any]]) -> JobRecord:
        job = JobRecord(job_id=str(uuid.uuid4()), name=name, status="queued", created_at=datetime.now(UTC).isoformat())
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


class BuyerClientState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jobs = JobManager()
        self._lock = threading.Lock()
        self._auth_token: str | None = None
        self._current_user: dict[str, Any] | None = None
        self._catalog: list[dict[str, Any]] = []
        self._current_order: dict[str, Any] | None = None
        self._current_access_code: dict[str, Any] | None = None
        self._runtime_session: dict[str, Any] | None = None
        self._bootstrap_config: dict[str, Any] | None = None
        self._last_env_report: dict[str, Any] | None = None
        self._workspace_path: str | None = None
        self._wireguard_state: dict[str, Any] | None = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def set_auth(self, token: str, user: dict[str, Any]) -> None:
        with self._lock:
            self._auth_token = token
            self._current_user = user

    def auth_token(self) -> str | None:
        with self._lock:
            return self._auth_token

    def set_catalog(self, catalog: list[dict[str, Any]]) -> None:
        with self._lock:
            self._catalog = catalog

    def set_order(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._current_order = payload.get("order")
            self._current_access_code = payload.get("access_code")

    def set_redeemed_access_code(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._current_access_code = payload.get("access_code")
            self._current_order = payload.get("order")

    def set_runtime_session(self, runtime_session: dict[str, Any], bootstrap_config: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._runtime_session = runtime_session
            if bootstrap_config is not None:
                self._bootstrap_config = bootstrap_config
        self.write_session_runtime_file()

    def set_env_report(self, env_report: dict[str, Any]) -> None:
        with self._lock:
            self._last_env_report = env_report
        self.write_session_runtime_file()

    def set_workspace_path(self, workspace_path: str) -> None:
        with self._lock:
            self._workspace_path = workspace_path
        self.write_session_runtime_file()

    def set_wireguard_state(self, payload: dict[str, Any] | None) -> None:
        with self._lock:
            self._wireguard_state = payload
        self.write_session_runtime_file()

    def current_runtime_session(self) -> dict[str, Any] | None:
        with self._lock:
            return self._runtime_session

    def current_bootstrap_config(self) -> dict[str, Any] | None:
        with self._lock:
            return self._bootstrap_config

    def current_workspace_path(self) -> str | None:
        with self._lock:
            return self._workspace_path

    def runtime_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "current_user": self._current_user,
                "catalog": self._catalog,
                "current_order": self._current_order,
                "current_access_code": self._current_access_code,
                "runtime_session": self._runtime_session,
                "bootstrap_config": self._bootstrap_config,
                "last_env_report": self._last_env_report,
                "workspace_path": self._workspace_path,
                "wireguard_state": self._wireguard_state,
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
            wireguard_dir=session_root / "wireguard",
        )

    def write_session_runtime_file(self) -> Path | None:
        runtime_session = self.current_runtime_session()
        if not runtime_session:
            return None
        paths = self.session_paths(runtime_session["id"])
        paths.session_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "backend_base_url": self.settings.backend_base_url,
            "backend_api_prefix": self.settings.backend_api_prefix,
            "auth_token": self.auth_token(),
            "snapshot": self.runtime_snapshot(),
        }
        paths.session_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return paths.session_file

    def start_heartbeat(self, backend_client: BackendClient, runtime_session_id: str) -> None:
        self.stop_heartbeat()
        self._heartbeat_stop.clear()

        def _run() -> None:
            while not self._heartbeat_stop.wait(self.settings.heartbeat_interval_seconds):
                try:
                    backend_client.heartbeat(runtime_session_id)
                except Exception:
                    continue

        self._heartbeat_thread = threading.Thread(target=_run, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)
        self._heartbeat_thread = None

    def cleanup_runtime_session(self, runtime_session_id: str) -> None:
        self.stop_heartbeat()
        paths = self.session_paths(runtime_session_id)
        for path in (paths.codex_dotdir / "config.toml", paths.codex_dotdir / "auth.json"):
            if path.exists():
                path.unlink()
        with self._lock:
            self._runtime_session = None
            self._bootstrap_config = None
            self._last_env_report = None
            self._workspace_path = None
            self._wireguard_state = None
        paths.session_root.mkdir(parents=True, exist_ok=True)
        (paths.session_root / "cleanup.json").write_text(
            json.dumps({"cleaned_at": datetime.now(UTC).isoformat()}, indent=2),
            encoding="utf-8",
        )
