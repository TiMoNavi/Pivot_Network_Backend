from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from seller_client_app.config import Settings
from seller_client_app.errors import LocalAppError
from seller_client_app.ubuntu_compute import run_ubuntu_shell


def pull_standard_image(settings: Settings, ubuntu_bootstrap: dict[str, Any]) -> dict[str, Any]:
    bootstrap = ubuntu_bootstrap["ubuntu_compute_bootstrap"]
    standard_image = bootstrap["seller_swarm_standard_image"]
    image_ref = standard_image["image_ref"]
    command = standard_image["pull_command"]
    ok, output = run_ubuntu_shell(settings, command, timeout=settings.standard_image_pull_timeout_seconds)
    if not ok:
        raise LocalAppError(
            step="ubuntu.standard_image.pull",
            code="standard_image_pull_failed",
            message="Failed to pull the platform seller swarm standard image in Ubuntu.",
            hint="Check Ubuntu Docker Engine, registry reachability, and backend-provided image_ref.",
            details={"image_ref": image_ref, "output": output},
            status_code=502,
        )

    inspect_ok, inspect_output = run_ubuntu_shell(
        settings,
        f"docker image inspect {shlex.quote(image_ref)} --format '{{{{json .RepoTags}}}}'",
        timeout=60,
    )
    return {
        "status": "pulled",
        "image_ref": image_ref,
        "description": standard_image.get("description"),
        "pull_command": command,
        "inspect_output": inspect_output if inspect_ok else output,
    }


def verify_standard_image(
    settings: Settings,
    ubuntu_bootstrap: dict[str, Any],
    *,
    session_id: str,
    requested_accelerator: str = "gpu",
) -> dict[str, Any]:
    bootstrap = ubuntu_bootstrap["ubuntu_compute_bootstrap"]
    standard_image = bootstrap["seller_swarm_standard_image"]
    image_ref = standard_image["image_ref"]
    verify_commands = list(standard_image.get("verify_commands") or [])
    gpu_enabled = requested_accelerator == "gpu"

    command_results: list[dict[str, Any]] = []
    for command in verify_commands:
        command_results.append(
            _run_standard_image_command(
                settings,
                image_ref,
                command,
                gpu_enabled=gpu_enabled,
            )
        )

    build_smoke = _run_host_build_smoke(settings, image_ref, session_id)
    network_probe = _run_host_network_probe(
        settings,
        bootstrap["swarm_join"]["manager_addr"],
        bootstrap["swarm_join"]["manager_port"],
    )

    overall_ok = all(item["ok"] for item in command_results) and build_smoke["ok"] and network_probe["ok"]
    if not overall_ok:
        raise LocalAppError(
            step="ubuntu.standard_image.verify",
            code="standard_image_verify_failed",
            message="Seller swarm standard image verification failed in Ubuntu.",
            hint="Review the failed verification command and ensure Ubuntu Docker, GPU, WireGuard, and network prerequisites are ready.",
            details={
                "image_ref": image_ref,
                "command_results": command_results,
                "build_smoke": build_smoke,
                "network_probe": network_probe,
            },
            status_code=502,
        )

    return {
        "status": "verified",
        "image_ref": image_ref,
        "command_results": command_results,
        "build_smoke": build_smoke,
        "network_probe": network_probe,
    }


def _run_standard_image_command(
    settings: Settings,
    image_ref: str,
    command: str,
    *,
    gpu_enabled: bool,
) -> dict[str, Any]:
    gpus_clause = "--gpus all " if gpu_enabled else ""
    script = (
        "set -euo pipefail\n"
        f"docker run --rm --network host {gpus_clause}"
        "-v /var/run/docker.sock:/var/run/docker.sock "
        f"{shlex.quote(image_ref)} /bin/bash -lc {shlex.quote(command)}\n"
    )
    ok, output = run_ubuntu_shell(settings, script, timeout=settings.standard_image_verify_timeout_seconds)
    return {
        "command": command,
        "ok": ok,
        "output": output,
    }


def _run_host_build_smoke(settings: Settings, image_ref: str, session_id: str) -> dict[str, Any]:
    smoke_tag = f"pivot-seller-build-smoke:{session_id[:12]}"
    script = f"""set -euo pipefail
tmpdir=$(mktemp -d)
cleanup() {{
  docker image rm -f {shlex.quote(smoke_tag)} >/dev/null 2>&1 || true
  rm -rf "$tmpdir"
}}
trap cleanup EXIT
cat >"$tmpdir/Dockerfile" <<'EOF'
FROM {image_ref}
RUN true
EOF
docker build -t {shlex.quote(smoke_tag)} "$tmpdir"
docker image inspect {shlex.quote(smoke_tag)} --format '{{{{json .Id}}}}'
"""
    ok, output = run_ubuntu_shell(settings, script, timeout=settings.standard_image_verify_timeout_seconds)
    return {
        "check": "host_build_smoke",
        "ok": ok,
        "output": output,
    }


def _run_host_network_probe(settings: Settings, host: str, port: int) -> dict[str, Any]:
    script = f"timeout 10 bash -lc 'cat < /dev/null > /dev/tcp/{host}/{port}'"
    ok, output = run_ubuntu_shell(settings, script, timeout=20)
    return {
        "check": "manager_network_probe",
        "ok": ok,
        "output": output or f"tcp {host}:{port} reachable",
        "host": host,
        "port": port,
    }
