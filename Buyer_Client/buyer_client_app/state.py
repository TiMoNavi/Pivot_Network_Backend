from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from buyer_client_app.config import Settings
from buyer_client_app.errors import LocalAppError


@dataclass(slots=True)
class SessionRuntimePaths:
    session_id: str
    session_root: Path
    session_file: Path
    logs_dir: Path
    workspace_dir: Path
    wireguard_dir: Path
    tasks_dir: Path


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


class BuyerClientState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._auth_token: str | None = None
        self._auth_expires_at: str | None = None
        self._current_user: dict[str, Any] | None = None
        self._window_session: WindowSessionRecord | None = None
        self._offers: list[dict[str, Any]] = []
        self._current_order: dict[str, Any] | None = None
        self._current_access_grant: dict[str, Any] | None = None
        self._active_access_grants: list[dict[str, Any]] = []
        self._current_runtime_plan: dict[str, Any] | None = None
        self._imported_grant_code: str | None = None
        self._current_runtime_session: dict[str, Any] | None = None
        self._wireguard_keypair: dict[str, Any] | None = None
        self._wireguard_state: dict[str, Any] | None = None
        self._workspace_selection: dict[str, Any] | None = None
        self._task_execution_history: list[dict[str, Any]] = []
        self._last_assistant_run: dict[str, Any] | None = None

    @classmethod
    def load_from_disk(cls, settings: Settings) -> "BuyerClientState":
        state = cls(settings)
        state_file = state.state_file_path()
        if not state_file.exists():
            return state
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return state
        state.restore_from_payload(payload)
        return state

    def restore_from_payload(self, payload: dict[str, Any]) -> None:
        snapshot = payload.get("snapshot") or {}
        with self._lock:
            self._auth_token = _optional_str(payload.get("auth_token"))
            self._auth_expires_at = _optional_str(payload.get("auth_expires_at"))
            self._current_user = _copy_dict(snapshot.get("current_user"))
            self._offers = _copy_list(snapshot.get("offers"))
            self._current_order = _copy_dict(snapshot.get("current_order"))
            self._current_access_grant = _copy_dict(snapshot.get("current_access_grant"))
            self._active_access_grants = _copy_list(snapshot.get("active_access_grants"))
            self._current_runtime_plan = _copy_dict(snapshot.get("runtime_access_plan"))
            self._imported_grant_code = _optional_str(snapshot.get("imported_grant_code"))
            self._current_runtime_session = _copy_dict(snapshot.get("runtime_session"))
            self._wireguard_keypair = _copy_dict(snapshot.get("wireguard_keypair"))
            self._wireguard_state = _copy_dict(snapshot.get("wireguard_state"))
            self._workspace_selection = _copy_dict(snapshot.get("workspace_selection"))
            self._task_execution_history = _copy_list(snapshot.get("task_execution_history"))
            self._last_assistant_run = _copy_dict(snapshot.get("last_assistant_run"))

            window_payload = snapshot.get("window_session")
            if isinstance(window_payload, dict) and window_payload.get("session_id"):
                self._window_session = WindowSessionRecord(
                    session_id=str(window_payload["session_id"]),
                    status=str(window_payload.get("status") or "active"),
                    opened_at=str(window_payload.get("opened_at") or ""),
                    last_heartbeat_at=str(window_payload.get("last_heartbeat_at") or ""),
                )
            else:
                self._window_session = None

    def state_root_path(self) -> Path:
        return self.settings.workspace_root_path / self.settings.state_subdir_name

    def state_file_path(self) -> Path:
        return self.state_root_path() / "buyer-client-state.json"

    def active_session_pointer_path(self) -> Path:
        return self.settings.workspace_root_path / self.settings.session_subdir_name / "active-session.json"

    def set_auth(self, token: str, user: dict[str, Any], expires_at: str | None) -> None:
        with self._lock:
            self._auth_token = token
            self._auth_expires_at = expires_at
            self._current_user = dict(user)
        self.write_session_runtime_file()

    def auth_token(self) -> str | None:
        with self._lock:
            return self._auth_token

    def current_user(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._current_user is None else dict(self._current_user)

    def update_current_user(self, user: dict[str, Any]) -> None:
        with self._lock:
            self._current_user = dict(user)
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
        return record.to_dict(self.settings.window_session_ttl_seconds)

    def current_window_session(self) -> dict[str, Any] | None:
        with self._lock:
            if self._window_session is None:
                return None
            return self._window_session.to_dict(self.settings.window_session_ttl_seconds)

    def require_window_session(self, session_id: str | None) -> dict[str, Any]:
        record = self.current_window_session()
        if record is None:
            raise LocalAppError(
                step="window_session",
                code="window_session_missing",
                message="Browser window session is not initialized.",
                hint="Reload the buyer client page to create a browser-scoped session.",
                status_code=401,
            )
        if not session_id:
            raise LocalAppError(
                step="window_session",
                code="window_session_header_missing",
                message="Window session header is missing.",
                hint="Use the buyer client browser page so requests include the active window session id.",
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
                hint="Reload the buyer client page to create a fresh browser session.",
                status_code=401,
            )
        return record

    def heartbeat_window_session(self, session_id: str) -> dict[str, Any]:
        self.require_window_session(session_id)
        with self._lock:
            assert self._window_session is not None
            self._window_session.last_heartbeat_at = datetime.now(UTC).isoformat()
            payload = self._window_session.to_dict(self.settings.window_session_ttl_seconds)
        self.write_session_runtime_file()
        return payload

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

    def set_offers(self, offers: list[dict[str, Any]]) -> None:
        with self._lock:
            self._offers = [dict(item) for item in offers]
        self.write_session_runtime_file()

    def set_current_order(self, order: dict[str, Any], runtime_plan: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._current_order = dict(order)
            self._current_access_grant = None
            self._current_runtime_plan = None if runtime_plan is None else dict(runtime_plan)
            self._current_runtime_session = None
        self.write_session_runtime_file()

    def set_activation(
        self,
        order: dict[str, Any],
        access_grant: dict[str, Any],
        runtime_plan: dict[str, Any],
    ) -> None:
        with self._lock:
            self._current_order = dict(order)
            self._current_access_grant = dict(access_grant)
            self._current_runtime_plan = dict(runtime_plan)
        self.write_session_runtime_file()

    def set_active_access_grants(self, grants: list[dict[str, Any]]) -> None:
        with self._lock:
            self._active_access_grants = [dict(item) for item in grants]
        self.write_session_runtime_file()

    def set_imported_grant_code(self, grant_code: str | None) -> None:
        with self._lock:
            self._imported_grant_code = _optional_str(grant_code)
        self.write_session_runtime_file()

    def imported_grant_code(self) -> str | None:
        with self._lock:
            return self._imported_grant_code

    def set_runtime_session(
        self,
        runtime_session: dict[str, Any],
        *,
        runtime_plan: dict[str, Any] | None = None,
        wireguard_keypair: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._current_runtime_session = dict(runtime_session)
            if runtime_plan is not None:
                self._current_runtime_plan = dict(runtime_plan)
            if wireguard_keypair is not None:
                self._wireguard_keypair = dict(wireguard_keypair)
        self.write_session_runtime_file()

    def current_runtime_session(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._current_runtime_session is None else dict(self._current_runtime_session)

    def set_wireguard_state(self, payload: dict[str, Any] | None) -> None:
        with self._lock:
            self._wireguard_state = None if payload is None else dict(payload)
        self.write_session_runtime_file()

    def current_wireguard_state(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._wireguard_state is None else dict(self._wireguard_state)

    def set_workspace_selection(self, payload: dict[str, Any] | None) -> None:
        with self._lock:
            self._workspace_selection = None if payload is None else dict(payload)
        self.write_session_runtime_file()

    def current_workspace_selection(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._workspace_selection is None else dict(self._workspace_selection)

    def current_wireguard_keypair(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._wireguard_keypair is None else dict(self._wireguard_keypair)

    def record_assistant_run(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_assistant_run = dict(payload)
        self.write_session_runtime_file()

    def last_assistant_run(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._last_assistant_run is None else dict(self._last_assistant_run)

    def refresh_from_disk(self) -> None:
        state_file = self.state_file_path()
        if not state_file.exists():
            return
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return
        if isinstance(payload, dict):
            self.restore_from_payload(payload)

    def record_task_execution(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._task_execution_history.append(dict(payload))
            self._task_execution_history = self._task_execution_history[-50:]
        self.write_session_runtime_file()

    def task_execution_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._task_execution_history]

    def current_order(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._current_order is None else dict(self._current_order)

    def current_access_grant(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._current_access_grant is None else dict(self._current_access_grant)

    def current_runtime_plan(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._current_runtime_plan is None else dict(self._current_runtime_plan)

    def runtime_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._runtime_snapshot_locked()

    def session_paths(self, session_id: str) -> SessionRuntimePaths:
        session_root = self.settings.workspace_root_path / self.settings.session_subdir_name / session_id
        return SessionRuntimePaths(
            session_id=session_id,
            session_root=session_root,
            session_file=session_root / "session.json",
            logs_dir=session_root / self.settings.logs_subdir_name,
            workspace_dir=session_root / self.settings.workspace_subdir_name,
            wireguard_dir=session_root / self.settings.wireguard_subdir_name,
            tasks_dir=session_root / self.settings.tasks_subdir_name,
        )

    def task_record_path(self, task_id: str) -> Path:
        session_key = self.current_session_key()
        if not session_key:
            raise LocalAppError(
                step="task.history",
                code="runtime_session_missing",
                message="Runtime session is not initialized.",
                hint="Create or refresh a runtime session before reading task history.",
                status_code=409,
            )
        return self.session_paths(session_key).tasks_dir / f"{task_id}.json"

    def read_task_execution(self, task_id: str) -> dict[str, Any] | None:
        record_path = self.task_record_path(task_id)
        if not record_path.exists():
            return None
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def write_task_execution_record(self, task_id: str, payload: dict[str, Any]) -> Path:
        record_path = self.task_record_path(task_id)
        record_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(record_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return record_path

    def current_session_key(self) -> str | None:
        with self._lock:
            return self._current_session_key_locked()

    def write_session_runtime_file(self) -> Path | None:
        payload: dict[str, Any]
        session_key: str | None
        with self._lock:
            payload = {
                "backend_base_url": self.settings.backend_base_url,
                "backend_api_prefix": self.settings.backend_api_prefix,
                "auth_token": self._auth_token,
                "auth_expires_at": self._auth_expires_at,
                "snapshot": self._runtime_snapshot_locked(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            session_key = self._current_session_key_locked()

        state_file = self.state_file_path()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(state_file, json.dumps(payload, ensure_ascii=False, indent=2))

        session_file: Path | None = None
        if session_key is not None:
            paths = self.session_paths(session_key)
            for directory in (paths.session_root, paths.logs_dir, paths.workspace_dir, paths.wireguard_dir, paths.tasks_dir):
                directory.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(paths.session_file, json.dumps(payload, ensure_ascii=False, indent=2))
            session_file = paths.session_file

        pointer_payload = {
            "session_id": session_key,
            "state_file": str(state_file),
            "session_file": None if session_file is None else str(session_file),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        pointer_path = self.active_session_pointer_path()
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(pointer_path, json.dumps(pointer_payload, ensure_ascii=False, indent=2))
        return session_file

    def reset_for_tests(self) -> None:
        with self._lock:
            self._auth_token = None
            self._auth_expires_at = None
            self._current_user = None
            self._window_session = None
            self._offers = []
            self._current_order = None
            self._current_access_grant = None
            self._active_access_grants = []
            self._current_runtime_plan = None
            self._imported_grant_code = None
            self._current_runtime_session = None
            self._wireguard_keypair = None
            self._wireguard_state = None
            self._workspace_selection = None
            self._task_execution_history = []
            self._last_assistant_run = None
        shutil.rmtree(self.state_root_path(), ignore_errors=True)
        shutil.rmtree(self.settings.workspace_root_path / self.settings.session_subdir_name, ignore_errors=True)

    def _current_session_key_locked(self) -> str | None:
        runtime_session_id = _optional_str((self._current_runtime_session or {}).get("id"))
        if runtime_session_id:
            return runtime_session_id
        if self._current_access_grant is not None:
            grant_runtime_session_id = _optional_str(self._current_access_grant.get("runtime_session_id"))
            if grant_runtime_session_id:
                return grant_runtime_session_id
            grant_id = _optional_str(self._current_access_grant.get("id"))
            if grant_id:
                return f"grant-{grant_id}"
        if self._imported_grant_code:
            return f"grant-code-{self._imported_grant_code[:12]}"
        if self._current_order is not None:
            order_id = _optional_str(self._current_order.get("id"))
            if order_id:
                return f"order-{order_id}"
        return None

    def _runtime_snapshot_locked(self) -> dict[str, Any]:
        session_key = self._current_session_key_locked()
        paths = self.session_paths(session_key) if session_key is not None else None
        return {
            "current_user": None if self._current_user is None else dict(self._current_user),
            "auth_session": None if self._auth_token is None else {"expires_at": self._auth_expires_at},
            "window_session": None if self._window_session is None else self._window_session.to_dict(self.settings.window_session_ttl_seconds),
            "offers": [dict(item) for item in self._offers],
            "current_order": None if self._current_order is None else dict(self._current_order),
            "current_access_grant": None if self._current_access_grant is None else dict(self._current_access_grant),
            "active_access_grants": [dict(item) for item in self._active_access_grants],
            "runtime_access_plan": None if self._current_runtime_plan is None else dict(self._current_runtime_plan),
            "imported_grant_code": self._imported_grant_code,
            "runtime_session": None if self._current_runtime_session is None else dict(self._current_runtime_session),
            "wireguard_keypair": None if self._wireguard_keypair is None else dict(self._wireguard_keypair),
            "wireguard_state": None if self._wireguard_state is None else dict(self._wireguard_state),
            "workspace_selection": None if self._workspace_selection is None else dict(self._workspace_selection),
            "task_execution_history": [dict(item) for item in self._task_execution_history],
            "last_assistant_run": None if self._last_assistant_run is None else dict(self._last_assistant_run),
            "paths": {
                "state_file": str(self.state_file_path()),
                "active_session_pointer": str(self.active_session_pointer_path()),
                "session_root": None if paths is None else str(paths.session_root),
                "session_file": None if paths is None else str(paths.session_file),
                "logs_dir": None if paths is None else str(paths.logs_dir),
                "workspace_dir": None if paths is None else str(paths.workspace_dir),
                "wireguard_dir": None if paths is None else str(paths.wireguard_dir),
                "tasks_dir": None if paths is None else str(paths.tasks_dir),
            },
        }


def _copy_dict(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _copy_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)
