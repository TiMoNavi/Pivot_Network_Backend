from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from seller_client_app.config import Settings
from seller_client_app.state import SellerClientState, SessionRuntimePaths


class CodexSessionError(Exception):
    pass


def prepare_codex_session(
    *,
    settings: Settings,
    state: SellerClientState,
    session_id: str,
    bootstrap_config: dict[str, Any],
) -> SessionRuntimePaths:
    paths = state.session_paths(session_id)
    paths.codex_dotdir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.workspace_dir.mkdir(parents=True, exist_ok=True)

    (paths.codex_dotdir / "config.toml").write_text(
        bootstrap_config["codex_config_toml"],
        encoding="utf-8",
    )
    (paths.codex_dotdir / "auth.json").write_text(
        bootstrap_config["codex_auth_json"],
        encoding="utf-8",
    )
    try:
        _register_mcp_server(settings, paths)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexSessionError(f"failed to register MCP server: {exc}") from exc
    return paths


def run_codex_assistant(
    *,
    settings: Settings,
    state: SellerClientState,
    session_id: str,
    user_message: str,
) -> dict[str, Any]:
    session_payload = state.current_onboarding_session()
    bootstrap = state.current_bootstrap_config()
    if not session_payload or not bootstrap:
        raise CodexSessionError("Onboarding session is not initialized.")

    paths = prepare_codex_session(
        settings=settings,
        state=state,
        session_id=session_id,
        bootstrap_config=bootstrap,
    )
    session_file = state.write_session_runtime_file()
    if session_file is None:
        raise CodexSessionError("Session runtime file is missing.")

    prompt = _build_assistant_prompt(state.runtime_snapshot(), user_message)
    output_file = paths.logs_dir / "assistant-last-message.txt"
    env = _codex_env(paths, session_file)
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
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    state.register_process(session_id, process)
    try:
        stdout, stderr = process.communicate(timeout=settings.codex_exec_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise CodexSessionError("codex exec timed out") from exc
    finally:
        state.stop_registered_process(session_id)

    if process.returncode != 0:
        raise CodexSessionError(stderr.strip() or stdout.strip() or "codex exec failed")

    last_message = output_file.read_text(encoding="utf-8").strip() if output_file.exists() else ""
    return {
        "assistant_message": last_message,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
        "log_file": str(output_file),
    }


def cleanup_codex_session(*, settings: Settings, state: SellerClientState, session_id: str) -> None:
    paths = state.session_paths(session_id)
    env = _codex_env(paths, paths.session_file)
    remove_command = _codex_command(settings) + [
        "mcp",
        "remove",
        settings.codex_mcp_server_name,
    ]
    try:
        subprocess.run(remove_command, env=env, check=False, capture_output=True, text=True, timeout=15)
    except Exception:  # noqa: BLE001
        pass
    state.cleanup_session(session_id)


def _register_mcp_server(settings: Settings, paths: SessionRuntimePaths) -> None:
    env = _codex_env(paths, paths.session_file)
    command = _codex_command(settings) + [
        "mcp",
        "add",
        settings.codex_mcp_server_name,
        "--env",
        f"SELLER_CLIENT_SESSION_FILE={paths.session_file}",
        "--env",
        f"PYTHONPATH={Path(__file__).resolve().parent.parent}",
        "--",
        sys.executable,
        "-m",
        "seller_client_app.mcp_server",
        "--session-file",
        str(paths.session_file),
    ]
    completed = subprocess.run(command, env=env, check=False, capture_output=True, text=True, timeout=30)
    if completed.returncode != 0 and "already exists" not in (completed.stderr or completed.stdout):
        raise CodexSessionError(completed.stderr.strip() or completed.stdout.strip() or "failed to register MCP server")


def _codex_env(paths: SessionRuntimePaths, session_file: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(paths.codex_home)
    env["SELLER_CLIENT_SESSION_FILE"] = str(session_file)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    return env


def _codex_command(settings: Settings) -> list[str]:
    candidate = shutil.which(settings.codex_command)
    if candidate:
        return _normalize_command_candidate(candidate)

    if os.name == "nt":
        for extra in ("codex.cmd", "codex.ps1"):
            resolved = shutil.which(extra)
            if resolved:
                return _normalize_command_candidate(resolved)

    raise CodexSessionError(f"Unable to locate Codex CLI command: {settings.codex_command}")


def _normalize_command_candidate(candidate: str) -> list[str]:
    lower = candidate.lower()
    if lower.endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-File", candidate]
    return [candidate]


def _build_assistant_prompt(snapshot: dict[str, Any], user_message: str) -> str:
    return (
        "You are the seller onboarding assistant for Pivot Network.\n"
        "Use only the configured MCP tools to inspect state and suggest or carry out controlled onboarding actions.\n"
        "If the user asks to sell their compute, join Swarm, or onboard the machine automatically, prefer the "
        "`sell_my_compute_full_auto` tool.\n"
        "Do not assume shell access. Do not ask the user to edit files by hand when a tool can do it.\n"
        "Current local state:\n"
        f"{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n\n"
        "User request:\n"
        f"{user_message}\n"
    )
