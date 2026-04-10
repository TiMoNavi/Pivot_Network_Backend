from __future__ import annotations

import platform
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from typing import Any

from buyer_client_app.backend import BackendClient
from buyer_client_app.config import Settings

CHECK_METADATA: dict[str, dict[str, Any]] = {
    "host_platform": {"title": "主机平台", "category": "host", "blocking": True, "hint": "buyer-client v1 的正式目标是 Windows 主机。"},
    "windows_version": {"title": "Windows 版本", "category": "host", "blocking": False, "hint": "建议使用 Windows 11 或较新的 Windows 10。"},
    "windows_admin": {"title": "管理员权限", "category": "host", "blocking": True, "hint": "启用临时 WireGuard 隧道通常需要管理员权限。"},
    "powershell": {"title": "PowerShell", "category": "host", "blocking": True, "hint": "本地配置与脚本执行依赖 PowerShell。"},
    "wireguard_client": {"title": "WireGuard 客户端", "category": "network", "blocking": True, "hint": "请安装 WireGuard Windows 客户端，确保 `wg.exe` 和 `wireguard.exe` 可用。"},
    "backend_reachability": {"title": "平台后端连通性", "category": "platform", "blocking": True, "hint": "请确认公网 HTTPS 域名可访问。"},
    "public_https": {"title": "公网 HTTPS", "category": "platform", "blocking": True, "hint": "buyer 控制面必须通过公网 HTTPS 访问。"},
    "codex_cli": {"title": "Codex CLI", "category": "assistant", "blocking": True, "hint": "自然语言连接助手依赖 Codex CLI。"},
}


def scan_environment(settings: Settings, backend_client: BackendClient | None = None) -> dict[str, Any]:
    system = platform.system()
    checks = [
        _check("host_platform", "pass" if system == "Windows" else "warn", f"Detected host platform: {system}", {"platform": system}),
        _check("windows_version", "pass" if system == "Windows" else "warn", platform.platform(), {"platform": platform.platform()}),
        _windows_admin_check(system),
        _command_check("powershell", ["powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]),
        _wireguard_client_check(),
    ]

    if backend_client is not None:
        checks.append(_backend_reachability_check(backend_client))
    else:
        checks.append(_check("backend_reachability", "fail", "Backend client is not configured."))

    checks.append(_https_check("public_https", settings.server_public_host, 443))
    checks.append(_codex_check())

    passed = sum(1 for item in checks if item["status"] == "pass")
    warned = sum(1 for item in checks if item["status"] == "warn")
    failed = sum(1 for item in checks if item["status"] == "fail")
    blocking_failed = [item["name"] for item in checks if item.get("blocking") and item["status"] == "fail"]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": system,
        "summary": {
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "blocking_failed": blocking_failed,
            "overall_status": "fail" if blocking_failed else ("warn" if warned else "pass"),
        },
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


def _run_command(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr or "").replace("\x00", "").strip()
    return completed.returncode == 0, output


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
        return _check("windows_admin", "warn", output)
    return _check("windows_admin", "pass" if output.lower() == "true" else "fail", output)


def _command_check(name: str, command: list[str]) -> dict[str, Any]:
    ok, output = _run_command(command)
    return _check(name, "pass" if ok else "fail", output or f"{name} not available")


def _wireguard_client_check() -> dict[str, Any]:
    candidates = []
    for name in ("wg", "wg.exe", "wireguard", "wireguard.exe"):
        path = shutil.which(name)
        if path:
            candidates.append(path)
    status = "pass" if candidates else "fail"
    detail = "WireGuard binaries resolved." if candidates else "WireGuard client binaries were not found."
    return _check("wireguard_client", status, detail, {"paths": candidates})


def _backend_reachability_check(backend_client: BackendClient) -> dict[str, Any]:
    try:
        payload = backend_client.health()
    except Exception as exc:  # noqa: BLE001
        return _check("backend_reachability", "fail", str(exc))
    return _check("backend_reachability", "pass", "Backend health endpoint reachable.", payload)


def _https_check(name: str, host: str, port: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=5):
            return _check(name, "pass", f"TCP {host}:{port} reachable.")
    except OSError as exc:
        return _check(name, "fail", f"TCP {host}:{port} unreachable: {exc}")


def _codex_check() -> dict[str, Any]:
    candidates = []
    for name in ("codex", "codex.cmd", "codex.ps1"):
        path = shutil.which(name)
        if path:
            candidates.append(path)
    if not candidates:
        return _check("codex_cli", "fail", "Codex CLI is not available on this host.")
    ok, output = _run_command([candidates[0], "--version"] if not candidates[0].lower().endswith(".ps1") else ["powershell.exe", "-NoProfile", "-File", candidates[0], "--version"])
    return _check("codex_cli", "pass" if ok else "fail", output or "Codex CLI check failed", {"path": candidates[0]})
