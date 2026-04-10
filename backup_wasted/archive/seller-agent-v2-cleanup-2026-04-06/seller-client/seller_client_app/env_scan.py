from __future__ import annotations

import platform
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from typing import Any

from seller_client_app.backend import BackendClient
from seller_client_app.config import Settings
from seller_client_app.ubuntu_compute import scan_ubuntu_compute

CHECK_METADATA: dict[str, dict[str, Any]] = {
    "host_platform": {
        "title": "主机平台",
        "category": "host",
        "blocking": True,
        "hint": "卖家控制台 v1 以 Windows 主机为正式目标环境。",
    },
    "windows_version": {
        "title": "Windows 版本",
        "category": "host",
        "blocking": False,
        "hint": "建议使用 Windows 11 或较新的 Windows 10 版本。",
    },
    "windows_admin": {
        "title": "管理员权限",
        "category": "host",
        "blocking": True,
        "hint": "请用管理员权限打开 PowerShell 或提升当前终端。",
    },
    "powershell": {
        "title": "PowerShell",
        "category": "host",
        "blocking": True,
        "hint": "本地脚本依赖 PowerShell 执行安装、检测和启动。",
    },
    "docker_desktop": {
        "title": "Docker Desktop",
        "category": "docker",
        "blocking": True,
        "hint": "请先安装并启动 Docker Desktop，再重试。",
    },
    "wsl2": {
        "title": "WSL2",
        "category": "docker",
        "blocking": True,
        "hint": "请确认 WSL2 已启用，且 Docker Desktop 已启用 WSL 集成。",
    },
    "wireguard": {
        "title": "WireGuard",
        "category": "network",
        "blocking": False,
        "hint": "卖家加入主线走公网；WireGuard 建议保持可用，用于后续内网链路与远程支持。",
    },
    "ssh_client": {
        "title": "SSH 客户端",
        "category": "support",
        "blocking": False,
        "hint": "SSH 主要用于远程协助和运维排障，不阻塞卖家公网加入。",
    },
    "ssh_server": {
        "title": "SSH 服务端",
        "category": "support",
        "blocking": False,
        "hint": "建议保持 sshd 可用，便于后续平台远程支持。",
    },
    "backend_reachability": {
        "title": "平台后端连通性",
        "category": "platform",
        "blocking": True,
        "hint": "请确认 `https://pivotcompute.store` 可访问，且网络未被本机代理错误拦截。",
    },
    "server_public_ssh": {
        "title": "公网 SSH 连通性",
        "category": "support",
        "blocking": False,
        "hint": "这不是卖家加入阻塞项，但建议保持可达用于后续支持。",
    },
    "server_wireguard_ssh": {
        "title": "WireGuard SSH 连通性",
        "category": "support",
        "blocking": False,
        "hint": "这不是卖家加入阻塞项，但有助于后续维护与排障。",
    },
    "gpu_presence": {
        "title": "GPU 检测",
        "category": "gpu",
        "blocking": False,
        "hint": "如果卖家希望提供 GPU 算力，这里应看到可用显卡。",
    },
    "docker_gpu_smoke": {
        "title": "Docker GPU 运行验证",
        "category": "gpu",
        "blocking": False,
        "hint": "如果 GPU 机器在这里失败，请检查 Docker Desktop 的 GPU 支持和 NVIDIA 驱动。",
    },
    "codex_cli": {
        "title": "Codex CLI",
        "category": "assistant",
        "blocking": True,
        "hint": "自然语言助手依赖 Codex CLI，可通过 npm 或现成安装包修复。",
    },
    "ubuntu_distro": {
        "title": "Ubuntu Compute 发行版",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "seller compute v2 需要专用的 WSL Ubuntu 发行版。",
    },
    "ubuntu_apt": {
        "title": "Ubuntu apt",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "Ubuntu compute 需要 apt 以安装 docker.io 和 wireguard-tools。",
    },
    "ubuntu_docker_cli": {
        "title": "Ubuntu Docker CLI",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "真正的 seller compute node 必须使用 Ubuntu 中的 Docker CLI/Engine。",
    },
    "ubuntu_dockerd": {
        "title": "Ubuntu dockerd",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "Ubuntu compute 必须有原生 dockerd，不能只依赖 Windows Docker Desktop。",
    },
    "ubuntu_wireguard": {
        "title": "Ubuntu WireGuard",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "Ubuntu compute 需要 wireguard-tools，并通过独立 peer 加入平台网络。",
    },
    "ubuntu_workspace_root": {
        "title": "Ubuntu 工作目录",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "Ubuntu compute 需要稳定的工作目录用于 build context 和运行时工作区。",
    },
    "ubuntu_swarm_info": {
        "title": "Ubuntu Swarm 信息",
        "category": "swarm",
        "blocking": False,
        "hint": "用于确认真正的 seller compute node 是否在 Ubuntu Docker 中加入了 Swarm。",
    },
}


def scan_environment(settings: Settings, backend_client: BackendClient | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    system = platform.system()
    checks.append(
        _check(
            "host_platform",
            "pass" if system == "Windows" else "warn",
            f"Detected host platform: {system}",
            {"platform": system},
        )
    )

    checks.append(_windows_version_check(system))
    checks.append(_windows_admin_check(system))
    checks.append(_command_check("powershell", ["powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]))
    checks.append(_docker_desktop_check(system))
    checks.append(_wsl_check(system))
    checks.append(_wireguard_check(system, settings.wireguard_interface_name))
    checks.append(_ssh_client_check())
    checks.append(_ssh_server_check(system))

    if backend_client is not None:
        checks.append(_backend_reachability_check(backend_client))
    else:
        checks.append(_check("backend_reachability", "warn", "Backend client not configured."))

    checks.append(
        _tcp_check(
            "server_public_ssh",
            settings.server_public_host,
            settings.server_public_ssh_port,
        )
    )
    checks.append(
        _tcp_check(
            "server_wireguard_ssh",
            settings.server_wireguard_ip,
            settings.server_wireguard_ssh_port,
        )
    )
    checks.append(_gpu_check())
    checks.append(_docker_gpu_smoke_check(settings))
    checks.append(_codex_check())
    ubuntu_report = scan_ubuntu_compute(settings) if system == "Windows" else {"distribution_name": settings.ubuntu_distribution_name, "checks": []}
    checks.extend(ubuntu_report["checks"])

    passed = sum(1 for item in checks if item["status"] == "pass")
    warned = sum(1 for item in checks if item["status"] == "warn")
    failed = sum(1 for item in checks if item["status"] == "fail")
    blocking_failed = [item["name"] for item in checks if item.get("blocking") and item["status"] == "fail"]
    blocking_warned = [item["name"] for item in checks if item.get("blocking") and item["status"] == "warn"]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": system,
        "summary": {
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "blocking_failed": blocking_failed,
            "blocking_warned": blocking_warned,
            "overall_status": "fail" if blocking_failed else ("warn" if warned or blocking_warned else "pass"),
        },
        "windows_host_checks": [item for item in checks if item.get("category") not in {"ubuntu_compute", "swarm"}],
        "ubuntu_compute_checks": [item for item in checks if item.get("category") == "ubuntu_compute"],
        "swarm_checks": [item for item in checks if item.get("category") == "swarm"],
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
    output = _sanitize_text((completed.stdout or completed.stderr or "").strip())
    return completed.returncode == 0, output


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
        return _check("windows_admin", "warn", output)
    return _check("windows_admin", "pass" if output.lower() == "true" else "warn", output)


def _command_check(name: str, command: list[str]) -> dict[str, Any]:
    ok, output = _run_command(command)
    return _check(name, "pass" if ok else "warn", output or f"{name} not available")


def _docker_desktop_check(system: str) -> dict[str, Any]:
    ok, output = _run_command(["docker", "info", "--format", "{{json .}}"])
    if ok:
        return _check("docker_desktop", "pass", "Docker CLI is reachable.", {"docker_info": output})
    if system != "Windows":
        return _check("docker_desktop", "warn", output or "Docker is not available on this host.")
    svc_ok, svc_output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Service -Name com.docker.service | Select-Object -ExpandProperty Status",
        ]
    )
    if svc_ok:
        return _check("docker_desktop", "warn", f"Docker service state: {svc_output}")
    return _check("docker_desktop", "fail", output or "Docker Desktop is not running.")


def _wsl_check(system: str) -> dict[str, Any]:
    if system != "Windows":
        return _check("wsl2", "warn", "WSL2 check is only available on Windows.")
    ok, output = _run_command(["wsl", "-l", "-v"])
    if not ok:
        return _check("wsl2", "fail", output or "WSL2 is not available.")
    return _check("wsl2", "pass", "WSL2 is available.", {"distributions": output})


def _wireguard_check(system: str, interface_name: str) -> dict[str, Any]:
    if system != "Windows":
        return _check("wireguard", "warn", "WireGuard service check is only available on Windows.")
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
        return _check("wireguard", "fail", output or "WireGuard service check failed.")
    status = "pass" if output.lower() == "running" else "warn"
    return _check("wireguard", status, f"{service_name}: {output}")


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


def _backend_reachability_check(backend_client: BackendClient) -> dict[str, Any]:
    try:
        payload = backend_client.health()
    except Exception as exc:  # noqa: BLE001
        return _check("backend_reachability", "fail", str(exc))
    return _check("backend_reachability", "pass", "Backend health endpoint reachable.", payload)


def _tcp_check(name: str, host: str, port: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=5):
            return _check(name, "pass", f"TCP {host}:{port} reachable.")
    except OSError as exc:
        return _check(name, "warn", f"TCP {host}:{port} unreachable: {exc}")


def _gpu_check() -> dict[str, Any]:
    ok, output = _run_command(["nvidia-smi", "-L"])
    if not ok:
        return _check("gpu_presence", "warn", output or "nvidia-smi not available")
    devices = [line.strip() for line in output.splitlines() if line.strip()]
    return _check("gpu_presence", "pass", f"Detected {len(devices)} GPU(s).", {"devices": devices})


def _docker_gpu_smoke_check(settings: Settings) -> dict[str, Any]:
    ok, output = _run_command(
        [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "--entrypoint",
            "nvidia-smi",
            settings.gpu_smoke_image,
            "-L",
        ]
    )
    status = "pass" if ok else "warn"
    detail = "Docker GPU smoke test passed." if ok else (output or "Docker GPU smoke test failed.")
    return _check("docker_gpu_smoke", status, detail, {"image": settings.gpu_smoke_image, "output": output})


def _codex_check() -> dict[str, Any]:
    codex_command = _resolve_codex_command()
    if codex_command is None:
        return _check("codex_cli", "warn", "Codex CLI is not available on this host.")
    ok, output = _run_command(codex_command + ["--version"])
    return _check("codex_cli", "pass" if ok else "warn", output or "codex CLI not available")


def _sanitize_text(value: str) -> str:
    return value.replace("\x00", "")


def _resolve_codex_command() -> list[str] | None:
    for candidate in ("codex", "codex.cmd", "codex.ps1"):
        resolved = shutil.which(candidate)
        if not resolved:
            continue
        if resolved.lower().endswith(".ps1"):
            return ["powershell.exe", "-NoProfile", "-File", resolved]
        return [resolved]
    return None
