from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seller_client_app.config import Settings
from seller_client_app.ubuntu_compute import run_ubuntu_shell


class UbuntuImageBuilderError(Exception):
    pass


@dataclass
class UbuntuBuildArtifact:
    image_ref: str
    repository: str
    tag: str
    registry: str
    ubuntu_context_path: str
    ubuntu_dockerfile_path: str
    local_metadata_path: Path
    local_dockerfile_path: Path


FROM_PATTERN = re.compile(r"^\s*FROM\s+([^\s]+)", re.IGNORECASE)


def generate_dockerfile_template(policy: dict[str, Any], extra_dockerfile_lines: list[str] | None = None) -> str:
    lines = [
        f"FROM {policy['allowed_runtime_base_image']}",
        'LABEL io.pivot.runtime.contract_version="v2"',
        'LABEL io.pivot.runtime.seller_build_host="wsl_ubuntu"',
        "",
        "# Add seller-specific runtime setup below without replacing the managed base image.",
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
        raise UbuntuImageBuilderError(
            f"Dockerfile base image must be `{expected_base_image}`, got `{actual or 'missing'}`."
        )


def build_image_in_ubuntu(
    *,
    settings: Settings,
    session_runtime_dir: Path,
    policy: dict[str, Any],
    repository: str,
    tag: str,
    registry: str,
    dockerfile_content: str,
    ubuntu_context_path: str,
    resource_profile: dict[str, Any] | None = None,
) -> UbuntuBuildArtifact:
    if not ubuntu_context_path.strip():
        raise UbuntuImageBuilderError("Ubuntu build context path is required.")

    validate_dockerfile_base_image(dockerfile_content, policy["allowed_runtime_base_image"])

    work_dir = session_runtime_dir / "builds" / _safe_slug(f"{repository}-{tag}")
    work_dir.mkdir(parents=True, exist_ok=True)

    local_dockerfile_path = work_dir / "Dockerfile.pivot.generated"
    local_dockerfile_path.write_text(dockerfile_content, encoding="utf-8")

    local_metadata_path = work_dir / "build-metadata.json"
    local_metadata_path.write_text(
        json.dumps(
            {
                "repository": repository,
                "tag": tag,
                "registry": registry,
                "ubuntu_context_path": ubuntu_context_path,
                "resource_profile": resource_profile or {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    image_ref = _compose_image_ref(registry, repository, tag)
    ubuntu_context = ubuntu_context_path.rstrip("/")
    ubuntu_dockerfile_path = f"{ubuntu_context}/Dockerfile.pivot.generated"
    script = (
        "set -euo pipefail\n"
        f"test -d {_shell_quote(ubuntu_context)}\n"
        f"cat > {_shell_quote(ubuntu_dockerfile_path)} <<'PIVOT_DOCKERFILE'\n"
        f"{dockerfile_content}\n"
        "PIVOT_DOCKERFILE\n"
        f"docker build -f {_shell_quote(ubuntu_dockerfile_path)} -t {_shell_quote(image_ref)} "
        f"{_shell_quote(ubuntu_context)}\n"
    )
    ok, output = run_ubuntu_shell(settings, script, timeout=3600)
    if not ok:
        raise UbuntuImageBuilderError(output or "Ubuntu docker build failed.")

    return UbuntuBuildArtifact(
        image_ref=image_ref,
        repository=repository,
        tag=tag,
        registry=registry,
        ubuntu_context_path=ubuntu_context,
        ubuntu_dockerfile_path=ubuntu_dockerfile_path,
        local_metadata_path=local_metadata_path,
        local_dockerfile_path=local_dockerfile_path,
    )


def push_image_from_ubuntu(settings: Settings, image_ref: str) -> None:
    script = (
        "set -euo pipefail\n"
        f"docker push {_shell_quote(image_ref)}\n"
    )
    ok, output = run_ubuntu_shell(settings, script, timeout=3600)
    if not ok:
        raise UbuntuImageBuilderError(output or "Ubuntu docker push failed.")


def _compose_image_ref(registry: str, repository: str, tag: str) -> str:
    if registry:
        return f"{registry.rstrip('/')}/{repository}:{tag}"
    return f"{repository}:{tag}"


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower() or "artifact"


def _shell_quote(value: str) -> str:
    return shlex.quote(value)
