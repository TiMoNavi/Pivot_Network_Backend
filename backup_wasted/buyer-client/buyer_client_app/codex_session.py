from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from buyer_client_app.config import Settings
from buyer_client_app.errors import LocalAppError
from buyer_client_app.state import BuyerClientState, SessionRuntimePaths


def prepare_codex_session(
    *,
    settings: Settings,
    state: BuyerClientState,
    runtime_session_id: str,
    bootstrap_config: dict[str, Any],
) -> SessionRuntimePaths:
    paths = state.session_paths(runtime_session_id)
    paths.codex_dotdir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.workspace_dir.mkdir(parents=True, exist_ok=True)
    (paths.codex_dotdir / "config.toml").write_text(bootstrap_config["codex_config_toml"], encoding="utf-8")
    (paths.codex_dotdir / "auth.json").write_text(bootstrap_config["codex_auth_json"], encoding="utf-8")
    try:
        _register_mcp_server(settings, paths)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalAppError(
            step="buyer.codex",
            code="buyer_codex_init_failed",
            message="Failed to initialize the buyer session-scoped Codex environment.",
            hint="Confirm Codex CLI is installed and callable on this machine.",
            details={"exception": str(exc)},
            status_code=500,
        ) from exc
    return paths


def run_codex_assistant(
    *,
    settings: Settings,
    state: BuyerClientState,
    runtime_session_id: str,
    user_message: str,
) -> dict[str, Any]:
    runtime_session = state.current_runtime_session()
    bootstrap = state.current_bootstrap_config()
    if not runtime_session or not bootstrap:
        raise LocalAppError(
            step="buyer.assistant",
            code="buyer_runtime_session_missing",
            message="Buyer runtime session is not initialized.",
            hint="Create a buyer runtime session before using the assistant.",
            status_code=409,
        )
    paths = prepare_codex_session(settings=settings, state=state, runtime_session_id=runtime_session_id, bootstrap_config=bootstrap)
    session_file = state.write_session_runtime_file()
    if session_file is None:
        raise LocalAppError(
            step="buyer.assistant",
            code="buyer_session_file_missing",
            message="Buyer runtime session metadata file is missing.",
            hint="Retry after reloading the buyer runtime session.",
            status_code=500,
        )
    output_file = paths.logs_dir / "assistant-last-message.txt"
    env = _codex_env(paths, session_file)
    prompt = (
        "You are the Pivot buyer runtime assistant.\n"
        "Use only MCP tools. Help the buyer connect, inspect the shell URL, and sync a local workspace.\n"
        f"Current state:\n{json.dumps(state.runtime_snapshot(), ensure_ascii=False, indent=2)}\n\n"
        f"User request:\n{user_message}\n"
    )
    command = _codex_command(settings) + [
        "exec",
        "--skip-git-repo-check",
        "-s",
        "read-only",
        "--cd",
        str(paths.workspace_dir),
        "-o",
        str(output_file),
        prompt,
    ]
    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = process.communicate(timeout=settings.codex_exec_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise LocalAppError(
            step="buyer.assistant",
            code="buyer_codex_timeout",
            message="Buyer assistant request timed out.",
            hint="Retry with a shorter request after checking local Codex responsiveness.",
            status_code=504,
        ) from exc
    if process.returncode != 0:
        raise LocalAppError(
            step="buyer.assistant",
            code="buyer_codex_failed",
            message="Codex assistant failed for the buyer runtime session.",
            hint="Inspect Codex logs and MCP tool availability, then retry.",
            details={"stdout": stdout.strip(), "stderr": stderr.strip()},
            status_code=500,
        )
    return {
        "assistant_message": output_file.read_text(encoding="utf-8").strip() if output_file.exists() else "",
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
        "log_file": str(output_file),
    }


def cleanup_codex_session(*, settings: Settings, state: BuyerClientState, runtime_session_id: str) -> None:
    paths = state.session_paths(runtime_session_id)
    env = _codex_env(paths, paths.session_file)
    try:
        subprocess.run(
            _codex_command(settings) + ["mcp", "remove", settings.codex_mcp_server_name],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:  # noqa: BLE001
        pass
    state.cleanup_runtime_session(runtime_session_id)


def _register_mcp_server(settings: Settings, paths: SessionRuntimePaths) -> None:
    env = _codex_env(paths, paths.session_file)
    command = _codex_command(settings) + [
        "mcp",
        "add",
        settings.codex_mcp_server_name,
        "--env",
        f"BUYER_CLIENT_SESSION_FILE={paths.session_file}",
        "--env",
        f"PYTHONPATH={Path(__file__).resolve().parent.parent}",
        "--",
        sys.executable,
        "-m",
        "buyer_client_app.mcp_server",
        "--session-file",
        str(paths.session_file),
    ]
    completed = subprocess.run(command, env=env, check=False, capture_output=True, text=True, timeout=30)
    if completed.returncode != 0 and "already exists" not in (completed.stderr or completed.stdout):
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "failed to register MCP server")


def _codex_env(paths: SessionRuntimePaths, session_file: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(paths.codex_home)
    env["BUYER_CLIENT_SESSION_FILE"] = str(session_file)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    return env


def _codex_command(settings: Settings) -> list[str]:
    candidate = shutil.which(settings.codex_command)
    if candidate:
        return _normalize_command(candidate)
    if os.name == "nt":
        for extra in ("codex.cmd", "codex.ps1"):
            resolved = shutil.which(extra)
            if resolved:
                return _normalize_command(resolved)
    raise RuntimeError(f"Unable to locate Codex CLI command: {settings.codex_command}")


def _normalize_command(candidate: str) -> list[str]:
    if candidate.lower().endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-File", candidate]
    return [candidate]
