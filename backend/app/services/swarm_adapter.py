from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from app.core.config import settings

SWARM_INFO_FORMAT = "{{json .Swarm}}"


class SwarmAdapterUnavailableError(RuntimeError):
    """Raised when the backend cannot query Docker Swarm through the CLI."""


def get_swarm_health() -> dict[str, Any]:
    docker_bin = settings.SWARM_DOCKER_BIN
    if shutil.which(docker_bin) is None:
        raise SwarmAdapterUnavailableError(
            f"Docker CLI '{docker_bin}' is not available in the backend runtime."
        )

    command = [docker_bin, "info", "--format", SWARM_INFO_FORMAT]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=settings.SWARM_DOCKER_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise SwarmAdapterUnavailableError(
            f"Docker CLI '{docker_bin}' is not available in the backend runtime."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SwarmAdapterUnavailableError(
            "Timed out while querying Docker Swarm from the backend runtime."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "docker info failed."
        raise SwarmAdapterUnavailableError(
            f"Docker Swarm query failed: {detail}"
        ) from exc

    swarm = _parse_swarm_payload(result.stdout)
    swarm_state = str(swarm.get("LocalNodeState") or "unknown")
    swarm_error = str(swarm.get("Error") or "").strip()

    return {
        "status": "ok" if swarm_state == "active" and not swarm_error else "degraded",
        "adapter": "docker-cli",
        "reachable": True,
        "swarm": {
            "state": swarm_state,
            "node_id": swarm.get("NodeID"),
            "node_addr": swarm.get("NodeAddr"),
            "control_available": bool(swarm.get("ControlAvailable")),
            "error": swarm_error or None,
        },
    }


def _parse_swarm_payload(raw_output: str) -> dict[str, Any]:
    payload = raw_output.strip()
    if not payload:
        raise SwarmAdapterUnavailableError(
            "Docker Swarm query returned an empty response."
        )

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SwarmAdapterUnavailableError(
            "Docker Swarm query returned invalid JSON."
        ) from exc

    if not isinstance(parsed, dict):
        raise SwarmAdapterUnavailableError(
            "Docker Swarm query returned an unexpected payload."
        )

    return parsed
