from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _wireguard_windows_exe() -> str | None:
    candidates = [
        shutil.which("wireguard"),
        shutil.which("wireguard.exe"),
        r"C:\Program Files\WireGuard\wireguard.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


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


def _wireguard_install_idempotent_success(result: dict[str, Any], action: str) -> bool:
    if action != "install_tunnel_service":
        return False
    message = f"{result.get('stdout') or ''} {result.get('stderr') or ''}".lower()
    return "tunnel already installed and running" in message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_request(request: dict[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    request_id = request.get("request_id")
    wireguard_exe = request.get("wireguard_exe") or _wireguard_windows_exe()
    if not wireguard_exe:
        return {"ok": False, "request_id": request_id, "error": "wireguard_exe_not_found", "action": action}

    if action == "install_tunnel_service":
        config_path = request.get("config_path") or ""
        result = _run_command([wireguard_exe, "/installtunnelservice", config_path])
    elif action == "uninstall_tunnel_service":
        interface_name = request.get("interface_name") or ""
        result = _run_command([wireguard_exe, "/uninstalltunnelservice", interface_name])
    else:
        return {"ok": False, "request_id": request_id, "error": "unsupported_action", "action": action}

    return {
        "ok": bool(result["ok"] or _wireguard_install_idempotent_success(result, action)),
        "request_id": request_id,
        "action": action,
        "timestamp": _now(),
        "result": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a privileged WireGuard action from a scheduled task.")
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--result-file", required=True)
    args = parser.parse_args()

    request_path = Path(args.request_file)
    result_path = Path(args.result_file)
    request_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    if not request_path.exists():
        result = {"ok": False, "error": "request_file_missing", "timestamp": _now()}
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = _process_request(request)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
