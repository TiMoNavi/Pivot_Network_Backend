from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from seller_client_app.config import Settings
from seller_client_app.state import SessionRuntimePaths


def active_codex_session_pointer_path(settings: Settings) -> Path:
    return settings.workspace_root_path / settings.session_subdir_name / "active-codex-session.json"


def write_active_codex_session_pointer(settings: Settings, paths: SessionRuntimePaths) -> Path:
    pointer_path = active_codex_session_pointer_path(settings)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": paths.session_id,
        "session_root": str(paths.session_root),
        "session_file": str(paths.session_file),
        "workspace_dir": str(paths.workspace_dir),
    }
    pointer_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pointer_path


def read_active_codex_session_pointer(settings: Settings, pointer_file: str | Path | None = None) -> dict[str, Any] | None:
    path = Path(pointer_file).expanduser() if pointer_file else active_codex_session_pointer_path(settings)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def resolve_active_session_file(settings: Settings, pointer_file: str | Path | None = None) -> Path:
    payload = read_active_codex_session_pointer(settings, pointer_file)
    if not isinstance(payload, dict):
        raise RuntimeError("active_codex_session_pointer_missing")
    session_file = Path(str(payload.get("session_file") or "")).expanduser()
    if not session_file.exists():
        raise RuntimeError("active_codex_session_file_missing")
    return session_file


def clear_active_codex_session_pointer(settings: Settings, session_id: str | None = None) -> None:
    pointer_path = active_codex_session_pointer_path(settings)
    if not pointer_path.exists():
        return
    if session_id is None:
        pointer_path.unlink(missing_ok=True)
        return
    payload = read_active_codex_session_pointer(settings)
    if isinstance(payload, dict) and str(payload.get("session_id") or "") == session_id:
        pointer_path.unlink(missing_ok=True)
