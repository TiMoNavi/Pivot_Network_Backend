from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seller_client_app.config import Settings


class DockerWorkbenchError(Exception):
    pass


@dataclass
class BuildArtifact:
    image_ref: str
    repository: str
    tag: str
    registry: str
    work_dir: Path
    dockerfile_path: Path
    metadata_path: Path


FROM_PATTERN = re.compile(r"^\s*FROM\s+([^\s]+)", re.IGNORECASE)


def generate_dockerfile_template(policy: dict[str, Any], extra_dockerfile_lines: list[str] | None = None) -> str:
    lines = [
        f"FROM {policy['allowed_runtime_base_image']}",
        "",
        "# Add your custom runtime setup below. Keep the managed base image unchanged.",
        "WORKDIR /workspace",
    ]
    for line in extra_dockerfile_lines or []:
        if line.strip():
            lines.append(line.rstrip())
    lines.extend(
        [
            "",
            'CMD ["/usr/local/bin/pivot-shell-agent"]',
            "",
        ]
    )
    return "\n".join(lines)


def extract_base_image(dockerfile_content: str) -> str | None:
    for raw_line in dockerfile_content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = FROM_PATTERN.match(raw_line)
        if match:
            return match.group(1)
        break
    return None


def validate_dockerfile_base_image(dockerfile_content: str, expected_base_image: str) -> None:
    actual = extract_base_image(dockerfile_content)
    if actual != expected_base_image:
        raise DockerWorkbenchError(
            f"Dockerfile base image must be `{expected_base_image}`, got `{actual or 'missing'}`."
        )


def build_image(
    *,
    settings: Settings,
    session_runtime_dir: Path,
    policy: dict[str, Any],
    repository: str,
    tag: str,
    registry: str,
    dockerfile_content: str,
    resource_profile: dict[str, Any] | None = None,
) -> BuildArtifact:
    if shutil.which("docker") is None:
        raise DockerWorkbenchError("Docker CLI is not available on this host.")

    validate_dockerfile_base_image(dockerfile_content, policy["allowed_runtime_base_image"])
    work_dir = session_runtime_dir / "builds" / _safe_slug(f"{repository}-{tag}")
    work_dir.mkdir(parents=True, exist_ok=True)
    dockerfile_path = work_dir / "Dockerfile"
    dockerfile_path.write_text(dockerfile_content, encoding="utf-8")

    metadata_path = work_dir / "build-metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "repository": repository,
                "tag": tag,
                "registry": registry,
                "resource_profile": resource_profile or {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    image_ref = _compose_image_ref(registry, repository, tag)
    _run_checked(["docker", "build", "-t", image_ref, str(work_dir)])
    return BuildArtifact(
        image_ref=image_ref,
        repository=repository,
        tag=tag,
        registry=registry,
        work_dir=work_dir,
        dockerfile_path=dockerfile_path,
        metadata_path=metadata_path,
    )


def push_image(image_ref: str) -> None:
    if shutil.which("docker") is None:
        raise DockerWorkbenchError("Docker CLI is not available on this host.")
    _run_checked(["docker", "push", image_ref])


def _compose_image_ref(registry: str, repository: str, tag: str) -> str:
    if registry:
        return f"{registry.rstrip('/')}/{repository}:{tag}"
    return f"{repository}:{tag}"


def _run_checked(command: list[str]) -> None:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DockerWorkbenchError(str(exc)) from exc
    if completed.returncode != 0:
        raise DockerWorkbenchError(completed.stderr.strip() or completed.stdout.strip() or "command_failed")


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower() or "artifact"
