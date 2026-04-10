from __future__ import annotations

import json
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

    def set_auth(self, token: str, user: dict[str, Any], expires_at: str | None) -> None:
        with self._lock:
            self._auth_token = token
            self._auth_expires_at = expires_at
            self._current_user = user
        self.write_session_runtime_file()

    def auth_token(self) -> str | None:
        with self._lock:
            return self._auth_token

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
            return self._window_session.to_dict(self.settings.window_session_ttl_seconds)

    def close_window_session(self, session_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            if self._window_session is None:
                return None
            if session_id and self._window_session.session_id != session_id:
                return None
            closed = self._window_session.to_dict(self.settings.window_session_ttl_seconds)
            closed["status"] = "closed"
            self._window_session = None
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

    def current_order(self) -> dict[str, Any] | None:
        with self._lock:
            return self._current_order

    def current_access_grant(self) -> dict[str, Any] | None:
        with self._lock:
            return self._current_access_grant

    def current_runtime_plan(self) -> dict[str, Any] | None:
        with self._lock:
            return self._current_runtime_plan

    def runtime_snapshot(self) -> dict[str, Any]:
        with self._lock:
            session_key = self._current_session_key_locked()
            paths = None
            if session_key is not None:
                session_paths = self.session_paths(session_key)
                paths = {
                    "session_root": str(session_paths.session_root),
                    "session_file": str(session_paths.session_file),
                    "logs_dir": str(session_paths.logs_dir),
                    "workspace_dir": str(session_paths.workspace_dir),
                }
            return {
                "current_user": self._current_user,
                "auth_session": None if self._auth_token is None else {"expires_at": self._auth_expires_at},
                "window_session": None if self._window_session is None else self._window_session.to_dict(self.settings.window_session_ttl_seconds),
                "offers": [dict(item) for item in self._offers],
                "current_order": None if self._current_order is None else dict(self._current_order),
                "current_access_grant": None if self._current_access_grant is None else dict(self._current_access_grant),
                "active_access_grants": [dict(item) for item in self._active_access_grants],
                "runtime_access_plan": None if self._current_runtime_plan is None else dict(self._current_runtime_plan),
                "paths": paths,
            }

    def session_paths(self, session_id: str) -> SessionRuntimePaths:
        session_root = self.settings.workspace_root_path / self.settings.session_subdir_name / session_id
        return SessionRuntimePaths(
            session_id=session_id,
            session_root=session_root,
            session_file=session_root / "session.json",
            logs_dir=session_root / self.settings.logs_subdir_name,
            workspace_dir=session_root / self.settings.workspace_subdir_name,
        )

    def write_session_runtime_file(self) -> Path | None:
        with self._lock:
            session_key = self._current_session_key_locked()
            if session_key is None:
                return None
            payload = {
                "backend_base_url": self.settings.backend_base_url,
                "backend_api_prefix": self.settings.backend_api_prefix,
                "auth_token": self._auth_token,
                "current_user": self._current_user,
                "window_session": None if self._window_session is None else self._window_session.to_dict(self.settings.window_session_ttl_seconds),
                "offers": self._offers,
                "current_order": self._current_order,
                "current_access_grant": self._current_access_grant,
                "active_access_grants": self._active_access_grants,
                "runtime_access_plan": self._current_runtime_plan,
                "workspace_root": str(self.settings.workspace_root_path),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        paths = self.session_paths(session_key)
        paths.session_root.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(paths.session_file, json.dumps(payload, ensure_ascii=False, indent=2))
        return paths.session_file

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

    def _current_session_key_locked(self) -> str | None:
        if self._current_access_grant is not None:
            runtime_session_id = str(self._current_access_grant.get("runtime_session_id") or "").strip()
            if runtime_session_id:
                return runtime_session_id
            grant_id = str(self._current_access_grant.get("id") or "").strip()
            if grant_id:
                return f"grant-{grant_id}"
        if self._current_order is not None:
            order_id = str(self._current_order.get("id") or "").strip()
            if order_id:
                return f"order-{order_id}"
        return None


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)
