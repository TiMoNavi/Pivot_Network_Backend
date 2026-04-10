from __future__ import annotations

import platform
import shutil
import subprocess
from datetime import UTC, datetime
from typing import Any

from seller_client_app.backend import BackendClient
from seller_client_app.config import Settings
from seller_client_app.ubuntu_compute import scan_ubuntu_compute

CHECK_METADATA: dict[str, dict[str, Any]] = {
    "host_platform": {
        "title": "主机平台",
        "category": "windows_host",
        "blocking": True,
        "hint": "seller v2 的正式控制台宿主是 Windows 主机。",
    },
    "windows_version": {
        "title": "Windows 版本",
        "category": "windows_host",
        "blocking": False,
        "hint": "建议使用较新的 Windows 11 或更新版 Windows 10。",
    },
    "windows_admin": {
        "title": "管理员权限",
        "category": "windows_host",
        "blocking": True,
        "hint": "请使用管理员权限打开 PowerShell，再执行 seller host 安装与引导。",
    },
    "powershell": {
        "title": "PowerShell",
        "category": "windows_host",
        "blocking": True,
        "hint": "seller host 的正式自动化流程依赖 PowerShell。",
    },
    "python311": {
        "title": "Python 3.11+",
        "category": "windows_host",
        "blocking": True,
        "hint": "本地 seller console 需要 Python 3.11+。",
    },
    "wsl2": {
        "title": "WSL2",
        "category": "windows_host",
        "blocking": True,
        "hint": "seller compute 必须运行在 WSL Ubuntu，而不是 Windows Docker Desktop。",
    },
    "ubuntu_distribution": {
        "title": "Ubuntu 发行版",
        "category": "windows_host",
        "blocking": True,
        "hint": "需要存在专用的 Ubuntu WSL 发行版供 seller compute 使用。",
    },
    "backend_reachability": {
        "title": "平台后端连通性",
        "category": "platform",
        "blocking": True,
        "hint": "seller 控制面仍统一通过公网 HTTPS 访问 Backend。",
    },
    "codex_cli": {
        "title": "Codex CLI",
        "category": "assistant",
        "blocking": True,
        "hint": "seller 会话级 Codex / MCP 助手依赖 Codex CLI。",
    },
    "wireguard_windows": {
        "title": "Windows WireGuard 支持",
        "category": "support",
        "blocking": False,
        "hint": "Windows WireGuard 仅作为支持链路，不是 seller 正式 compute 依赖。",
    },
    "ssh_client": {
        "title": "SSH 客户端",
        "category": "support",
        "blocking": False,
        "hint": "SSH 客户端有助于远程支持与排障。",
    },
    "ssh_server": {
        "title": "SSH 服务端",
        "category": "support",
        "blocking": False,
        "hint": "OpenSSH Server 仅用于支持与调试，不是 seller 正式阻塞项。",
    },
}


def scan_environment(settings: Settings, backend_client: BackendClient | None = None) -> dict[str, Any]:
    system = platform.system()

    windows_host_checks = [
        _host_platform_check(system),
        _windows_version_check(system),
        _windows_admin_check(system),
        _powershell_check(system),
        _python311_check(),
        _wsl_check(system),
        _ubuntu_distribution_check(system, settings.ubuntu_distribution_name),
    ]
    platform_checks = [
        _backend_reachability_check(backend_client)
        if backend_client is not None
        else _check("backend_reachability", "warn", "Backend client is not configured yet.")
    ]
    assistant_checks = [_codex_check()]
    support_checks = [
        _wireguard_windows_check(system, settings.wireguard_interface_name),
        _ssh_client_check(),
        _ssh_server_check(system),
    ]

    if system == "Windows":
        ubuntu_report = scan_ubuntu_compute(settings)
    else:
        ubuntu_report = {
            "distribution_name": settings.ubuntu_distribution_name,
            "summary": {"passed": 0, "warned": 0, "failed": 0, "overall_status": "warn"},
            "ubuntu_compute_checks": [],
            "swarm_checks": [],
            "checks": [],
        }

    runtime_contract_checks: list[dict[str, Any]] = []
    checks = [
        *windows_host_checks,
        *platform_checks,
        *assistant_checks,
        *support_checks,
        *ubuntu_report["ubuntu_compute_checks"],
        *ubuntu_report["swarm_checks"],
        *runtime_contract_checks,
    ]
    summary = _summarize(checks)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": system,
        "summary": summary,
        "windows_host_checks": windows_host_checks,
        "platform_checks": platform_checks,
        "assistant_checks": assistant_checks,
        "support_checks": support_checks,
        "ubuntu_compute_checks": ubuntu_report["ubuntu_compute_checks"],
        "swarm_checks": ubuntu_report["swarm_checks"],
        "runtime_contract_checks": runtime_contract_checks,
        "checks": checks,
    }


def _check(name: str, status: str, detail: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = CHECK_METADATA.get(name, {})
    return {
        "name": name,
        "title": meta.get("title", name),
        "category": meta.get("category", "general"),
        "status": status,
        "blocking": bool(meta.get("blocking", False)),
        "detail": detail,
        "hint": meta.get("hint"),
        "data": data or {},
    }


def _summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in checks if item["status"] == "pass")
    warned = sum(1 for item in checks if item["status"] == "warn")
    failed = sum(1 for item in checks if item["status"] == "fail")
    blocking_failed = [item["name"] for item in checks if item["blocking"] and item["status"] == "fail"]
    return {
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "blocking_failed": blocking_failed,
        "overall_status": "fail" if blocking_failed else ("warn" if warned or failed else "pass"),
    }


def _run_command(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr or "").replace("\x00", "").strip()
    return completed.returncode == 0, output


def _host_platform_check(system: str) -> dict[str, Any]:
    status = "pass" if system == "Windows" else "fail"
    return _check("host_platform", status, f"Detected host platform: {system}", {"platform": system})


def _windows_version_check(system: str) -> dict[str, Any]:
    detail = platform.platform()
    status = "pass" if system == "Windows" else "warn"
    return _check("windows_version", status, detail, {"platform": detail})


def _windows_admin_check(system: str) -> dict[str, Any]:
    if system != "Windows":
        return _check("windows_admin", "warn", "Administrator check is only available on Windows.")
    ok, output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)",
        ]
    )
    if not ok:
        return _check("windows_admin", "warn", output or "Failed to evaluate Windows administrator privilege.")
    status = "pass" if output.lower() == "true" else "fail"
    detail = "Administrator privilege detected." if status == "pass" else "Current shell is not elevated."
    return _check("windows_admin", status, detail)


def _powershell_check(system: str) -> dict[str, Any]:
    if system != "Windows":
        return _check("powershell", "warn", "PowerShell check is only available on Windows.")
    ok, output = _run_command(["powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"])
    return _check("powershell", "pass" if ok else "fail", output or "PowerShell is not available.")


def _python311_check() -> dict[str, Any]:
    python_command = shutil.which("python")
    py_launcher = shutil.which("py")
    if python_command:
        ok, output = _run_command([python_command, "--version"])
        if ok and output.startswith("Python 3."):
            minor = int(output.split(".")[1].split()[0])
            if minor >= 11:
                return _check("python311", "pass", output, {"command": python_command})
    if py_launcher:
        ok, output = _run_command([py_launcher, "-3.11", "--version"])
        if ok:
            return _check("python311", "pass", output, {"command": py_launcher})
    return _check("python311", "fail", "Python 3.11+ is not available on PATH.")


def _wsl_check(system: str) -> dict[str, Any]:
    if system != "Windows":
        return _check("wsl2", "warn", "WSL2 check is only available on Windows.")
    ok, output = _run_command(["wsl", "-l", "-v"])
    if not ok:
        return _check("wsl2", "fail", output or "WSL2 is not available.")
    return _check("wsl2", "pass", "WSL2 is available.", {"distributions": output})


def _ubuntu_distribution_check(system: str, distribution_name: str) -> dict[str, Any]:
    if system != "Windows":
        return _check("ubuntu_distribution", "warn", "Ubuntu distribution check is only available on Windows.")
    ok, output = _run_command(["wsl", "-l", "-v"])
    if not ok:
        return _check("ubuntu_distribution", "fail", output or "Failed to list WSL distributions.")
    found = any(distribution_name.lower() in line.lower() for line in output.splitlines())
    status = "pass" if found else "fail"
    detail = (
        f"Detected Ubuntu distribution: {distribution_name}"
        if found
        else f"WSL distribution `{distribution_name}` is missing."
    )
    return _check("ubuntu_distribution", status, detail, {"distributions": output})


def _backend_reachability_check(backend_client: BackendClient) -> dict[str, Any]:
    try:
        payload = backend_client.health()
    except Exception as exc:  # noqa: BLE001
        return _check("backend_reachability", "fail", str(exc))
    return _check("backend_reachability", "pass", "Backend health endpoint reachable.", payload)


def _codex_check() -> dict[str, Any]:
    command = _resolve_codex_command()
    if command is None:
        return _check("codex_cli", "fail", "Codex CLI is not available on this host.")
    ok, output = _run_command(command + ["--version"])
    return _check("codex_cli", "pass" if ok else "fail", output or "Codex CLI is not available.")


def _wireguard_windows_check(system: str, interface_name: str) -> dict[str, Any]:
    if system != "Windows":
        return _check("wireguard_windows", "warn", "Windows WireGuard support check is only available on Windows.")
    service_name = f"WireGuardTunnel${interface_name}"
    ok, output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"if (Get-Service -Name '{service_name}' -ErrorAction SilentlyContinue) {{ Get-Service -Name '{service_name}' | Select-Object -ExpandProperty Status }} else {{ 'missing' }}",
        ]
    )
    if not ok:
        return _check("wireguard_windows", "warn", output or "Windows WireGuard support check failed.")
    status = "pass" if output.lower() == "running" else "warn"
    return _check("wireguard_windows", status, f"{service_name}: {output}")


def _ssh_client_check() -> dict[str, Any]:
    ok, output = _run_command(["ssh", "-V"])
    return _check("ssh_client", "pass" if ok else "warn", output or "ssh client not available")


def _ssh_server_check(system: str) -> dict[str, Any]:
    if system != "Windows":
        return _check("ssh_server", "warn", "sshd service check is only available on Windows.")
    ok, output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "if (Get-Service -Name sshd -ErrorAction SilentlyContinue) { Get-Service -Name sshd | Select-Object -ExpandProperty Status } else { 'missing' }",
        ]
    )
    if not ok:
        return _check("ssh_server", "warn", output or "sshd service check failed.")
    return _check("ssh_server", "pass" if output.lower() == "running" else "warn", output)


def _resolve_codex_command() -> list[str] | None:
    for candidate in ("codex", "codex.cmd", "codex.ps1"):
        resolved = shutil.which(candidate)
        if not resolved:
            continue
        if resolved.lower().endswith(".ps1"):
            return ["powershell.exe", "-NoProfile", "-File", resolved]
        return [resolved]
    return None
