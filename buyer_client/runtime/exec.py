from __future__ import annotations

import subprocess
import time
from typing import Any


def _run_local_command(command: list[str]) -> dict[str, Any]:
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
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def find_local_service_container(service_name: str) -> dict[str, Any]:
    result = _run_local_command(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.swarm.service.name={service_name}",
            "--format",
            "{{.ID}}",
        ]
    )
    if not result["ok"]:
        return result
    container_id = next((line.strip() for line in result["stdout"].splitlines() if line.strip()), "")
    return {"ok": bool(container_id), "container_id": container_id, "source_result": result}


def exec_runtime_command_locally(service_name: str, command: str, wait_seconds: int = 20) -> dict[str, Any]:
    deadline = time.time() + wait_seconds
    container = find_local_service_container(service_name)
    while time.time() < deadline and not container.get("ok"):
        time.sleep(1)
        container = find_local_service_container(service_name)
    if not container.get("ok"):
        return {
            "ok": False,
            "error": "local_runtime_container_not_found",
            "service_name": service_name,
            "container_lookup": container,
        }
    exec_result = _run_local_command(["docker", "exec", str(container["container_id"]), "sh", "-lc", command])
    return {
        "ok": bool(exec_result["ok"]),
        "service_name": service_name,
        "container_id": container["container_id"],
        "stdout": exec_result["stdout"],
        "stderr": exec_result["stderr"],
        "exit_code": exec_result["returncode"],
        "exec_result": exec_result,
    }
