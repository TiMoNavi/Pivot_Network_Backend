from __future__ import annotations

import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from seller_client_app.config import Settings
from seller_client_app.errors import LocalAppError


def run_windows_host_install_and_check(
    settings: Settings,
    *,
    mode: str = "all",
    output_path: Path | None = None,
) -> dict[str, Any]:
    if platform.system() != "Windows":
        raise LocalAppError(
            step="windows_host.install_and_check",
            code="windows_only",
            message="Windows host install/check can only run on Windows.",
            hint="Run this step from the seller Windows host console.",
            status_code=409,
        )

    script_path = _resolve_windows_host_script()
    if not script_path.exists():
        raise LocalAppError(
            step="windows_host.install_and_check",
            code="script_missing",
            message="Windows host install/check script is missing.",
            hint="Ensure environment_check is deployed beside seller-client before running onboarding.",
            details={"expected_path": str(script_path)},
            status_code=500,
        )

    if output_path is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        output_path = Path(settings.workspace_root) / f"windows-host-check-{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    backend_health_url = f"{settings.backend_base_url.rstrip('/')}{settings.backend_api_prefix}/health"
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Mode",
        mode,
        "-BackendHealthUrl",
        backend_health_url,
        "-UbuntuDistribution",
        settings.ubuntu_distribution_name,
        "-OutputPath",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=settings.windows_host_script_timeout_seconds,
    )
    stdout = (completed.stdout or "").replace("\x00", "").strip()
    stderr = (completed.stderr or "").replace("\x00", "").strip()

    if not output_path.exists():
        raise LocalAppError(
            step="windows_host.install_and_check",
            code="script_report_missing",
            message="Windows host install/check did not produce a JSON report.",
            hint="Check the PowerShell output and rerun the Windows host script with administrator privileges.",
            details={"stdout": stdout, "stderr": stderr, "command": command},
            status_code=502,
        )

    report = json.loads(output_path.read_text(encoding="utf-8-sig"))
    report["stdout"] = stdout
    report["stderr"] = stderr
    report["command"] = command
    report["report_path"] = str(output_path)

    if completed.returncode != 0:
        raise LocalAppError(
            step="windows_host.install_and_check",
            code="script_failed",
            message="Windows host install/check script failed.",
            hint="Review the generated JSON report, then fix the blocking items before retrying.",
            details={"report": report},
            status_code=502,
        )

    return report


def _resolve_windows_host_script() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "environment_check" / "windows_seller_host_install_and_check.ps1"
