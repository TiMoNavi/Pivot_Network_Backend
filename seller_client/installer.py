from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seller_client.agent_mcp import _default_state_dir, _ensure_client_dirs, environment_check
from seller_client.windows_elevation import (
    current_user_task_identity,
    is_windows_platform,
    wireguard_helper_create_task_command,
    wireguard_helper_launcher_path,
    wireguard_helper_query_task_command,
    wireguard_helper_request_path,
    wireguard_helper_result_path,
    wireguard_helper_root,
    wireguard_helper_script_path,
    wireguard_helper_task_command,
    wireguard_helper_task_name,
    windows_is_elevated,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def codex_server_name() -> str:
    return "sellerNodeAgent"


def _toml_basic_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalized_path(value: str) -> str:
    if is_windows_platform():
        return value.replace("\\", "/")
    return value


def desired_mcp_block() -> str:
    python_exe = _normalized_path(shutil.which("python") or sys.executable)
    agent_path = repo_root() / "seller_client" / "agent_mcp.py"
    cwd_path = repo_root()
    return (
        f"\n[mcp_servers.{codex_server_name()}]\n"
        f"command = {_toml_basic_string(python_exe)}\n"
        f"args = [{_toml_basic_string(agent_path.as_posix())}]\n"
        f"cwd = {_toml_basic_string(cwd_path.as_posix())}\n"
    )


def codex_installed() -> bool:
    return shutil.which("codex") is not None


def _run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "ok": completed.returncode == 0,
    }


def _run_powershell(script: str) -> dict[str, Any]:
    return _run_command(["powershell", "-NoProfile", "-Command", script])


def windows_wireguard_helper_task_installed() -> bool:
    if not is_windows_platform():
        return False
    query = _run_powershell(
        (
            "$ErrorActionPreference='Stop'; "
            f"Get-ScheduledTask -TaskName '{wireguard_helper_task_name()}' | Out-Null; "
            "Write-Output 'INSTALLED'"
        )
    )
    return bool(query["ok"])


def ensure_windows_wireguard_helper_task(dry_run: bool = False) -> dict[str, Any]:
    if not is_windows_platform():
        return {"ok": True, "skipped": True, "reason": "not_windows"}

    helper_root = wireguard_helper_root()
    helper_root.mkdir(parents=True, exist_ok=True)
    python_exe = shutil.which("python") or sys.executable
    launcher_path = wireguard_helper_launcher_path()
    launcher_text = (
        "@echo off\r\n"
        f'"{python_exe}" "{wireguard_helper_script_path()}" '
        f'--request-file "{wireguard_helper_request_path()}" '
        f'--result-file "{wireguard_helper_result_path()}"\r\n'
    )
    if not dry_run:
        launcher_path.write_text(launcher_text, encoding="utf-8")
    task_exists = windows_wireguard_helper_task_installed()
    elevated = windows_is_elevated()
    if task_exists and (dry_run or not elevated):
        return {
            "ok": True,
            "changed": False,
            "task_name": wireguard_helper_task_name(),
            "launcher_path": str(launcher_path),
            "request_path": str(wireguard_helper_request_path()),
            "result_path": str(wireguard_helper_result_path()),
        }

    payload = {
        "task_name": wireguard_helper_task_name(),
        "task_command": wireguard_helper_task_command(),
        "launcher_path": str(launcher_path),
        "request_path": str(wireguard_helper_request_path()),
        "result_path": str(wireguard_helper_result_path()),
        "admin_required": True,
        "elevated": elevated,
        "force_recreate": bool(task_exists and elevated and not dry_run),
    }
    if dry_run:
        return {"ok": True, "changed": True, "dry_run": True, **payload}

    delete_result = None
    if task_exists:
        delete_result = _run_powershell(
            (
                "$ErrorActionPreference='SilentlyContinue'; "
                f"Unregister-ScheduledTask -TaskName '{wireguard_helper_task_name()}' -Confirm:$false -ErrorAction SilentlyContinue; "
                "Write-Output 'REMOVED'"
            )
        )
    create_script = (
        "$ErrorActionPreference='Stop'; "
        f"$action = New-ScheduledTaskAction -Execute '{launcher_path}'; "
        "$trigger = New-ScheduledTaskTrigger -Once -At ([datetime]'2000-01-01T23:59:00'); "
        f"$principal = New-ScheduledTaskPrincipal -UserId '{current_user_task_identity()}' "
        "-LogonType Interactive -RunLevel Highest; "
        f"Register-ScheduledTask -TaskName '{wireguard_helper_task_name()}' "
        "-Action $action -Trigger $trigger -Principal $principal -Force | Out-Null; "
        "Write-Output 'REGISTERED'"
    )
    create_result = _run_powershell(create_script)
    return {
        "ok": bool(create_result["ok"]),
        "changed": bool(create_result["ok"]),
        "delete_result": delete_result,
        "create_result": create_result,
        **payload,
    }


def mcp_attached_to_codex(config_text: str | None = None) -> bool:
    if config_text is None:
        path = codex_config_path()
        if not path.exists():
            return False
        config_text = path.read_text(encoding="utf-8")
    return f"[mcp_servers.{codex_server_name()}]" in config_text


def upsert_mcp_block(config_text: str, block: str) -> str:
    pattern = re.compile(
        rf"(?ms)^\[mcp_servers\.{re.escape(codex_server_name())}\]\n.*?(?=^\[|\Z)"
    )
    stripped = config_text.rstrip()
    if pattern.search(stripped):
        updated = pattern.sub(block.strip() + "\n\n", stripped, count=1)
        return updated.rstrip() + "\n"
    if not stripped:
        return block.lstrip()
    return stripped + block + "\n"


def attach_mcp_to_codex(dry_run: bool = False) -> dict[str, Any]:
    path = codex_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = upsert_mcp_block(existing, desired_mcp_block())
    changed = updated != existing
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return {"ok": True, "changed": changed, "config_path": str(path), "dry_run": dry_run}


def bootstrap_client(dry_run: bool = True, state_dir: str | None = None) -> dict[str, Any]:
    base_dir = Path(state_dir).expanduser().resolve() if state_dir else _default_state_dir()
    dirs = _ensure_client_dirs(base_dir)
    env = environment_check()
    codex_attach = attach_mcp_to_codex(dry_run=dry_run)
    windows_wireguard_helper = ensure_windows_wireguard_helper_task(dry_run=dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "repo_root": str(repo_root()),
        "state_dir": str(base_dir),
        "dirs": dirs,
        "environment": env,
        "codex_installed": codex_installed(),
        "codex_config_path": str(codex_config_path()),
        "mcp_attached": mcp_attached_to_codex(),
        "attach_result": codex_attach,
        "windows_wireguard_helper": windows_wireguard_helper,
        "needs_codex_install": not codex_installed(),
        "needs_docker_setup": not bool(env["docker_cli"]),
        "needs_wireguard_setup": not bool(env["wireguard_cli"] or env["wireguard_windows_exe"]),
        "needs_windows_wireguard_helper": bool(
            is_windows_platform()
            and (env["wireguard_cli"] or env["wireguard_windows_exe"])
            and not windows_wireguard_helper_task_installed()
        ),
        "windows_apply_command": (
            f"powershell -ExecutionPolicy Bypass -File \"{repo_root() / 'seller_client' / 'install_windows.ps1'}\" -Apply"
            if is_windows_platform()
            else ""
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seller client bootstrap installer skeleton.")
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--apply", action="store_true", help="Write config changes instead of dry-run.")
    args = parser.parse_args()

    result = bootstrap_client(dry_run=not args.apply, state_dir=args.state_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
