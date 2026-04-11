from __future__ import annotations

import hashlib
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from buyer_client_app.errors import LocalAppError

MAX_INTERFACE_NAME_LENGTH = 15


def generate_keypair() -> tuple[str, str]:
    wg_bin = _resolve_wg_binary()
    try:
        private_key = subprocess.run(
            [wg_bin, "genkey"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout.strip()
        public_key = subprocess.run(
            [wg_bin, "pubkey"],
            input=private_key + "\n",
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise LocalAppError(
            step="wireguard.keys",
            code="wireguard_key_generation_failed",
            message="Failed to generate a WireGuard keypair on this machine.",
            hint=_wireguard_install_hint("wg"),
            details={"exception": str(exc)},
            status_code=500,
        ) from exc
    if not private_key or not public_key:
        raise LocalAppError(
            step="wireguard.keys",
            code="wireguard_key_generation_empty",
            message="WireGuard key generation returned empty output.",
            hint=_wireguard_install_hint("wg"),
            status_code=500,
        )
    return private_key, public_key


def write_config(
    *,
    config_path: Path,
    private_key: str,
    profile: dict[str, Any],
) -> None:
    client_address = _normalize_client_address(profile.get("client_address"))
    server_public_key = str(profile.get("server_public_key") or "").strip()
    endpoint_host = str(profile.get("endpoint_host") or "").strip()
    endpoint_port = profile.get("endpoint_port")
    allowed_ips = list(profile.get("allowed_ips") or [])

    if not client_address or not server_public_key or not endpoint_host or endpoint_port is None or not allowed_ips:
        raise LocalAppError(
            step="wireguard.config",
            code="wireguard_profile_incomplete",
            message="The buyer WireGuard profile is incomplete.",
            hint="Refresh the runtime session and retry after bootstrap material is available.",
            details={"profile": profile},
            status_code=409,
        )

    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {client_address}",
        "",
        "[Peer]",
        f"PublicKey = {server_public_key}",
        f"Endpoint = {endpoint_host}:{endpoint_port}",
        f"AllowedIPs = {', '.join(str(item) for item in allowed_ips)}",
    ]
    if profile.get("persistent_keepalive") is not None:
        lines.append(f"PersistentKeepalive = {profile['persistent_keepalive']}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_interface_name(prefix: str, session_id: str) -> str:
    safe_prefix = re.sub(r"[^a-zA-Z0-9.+-]", "-", str(prefix or "").strip().lower()).strip("-.")
    if not safe_prefix:
        safe_prefix = "wg"

    session_hash = hashlib.sha1(str(session_id or "").encode("utf-8")).hexdigest()[:8]
    budget = MAX_INTERFACE_NAME_LENGTH - len(session_hash) - 1
    if budget < 1:
        return session_hash[:MAX_INTERFACE_NAME_LENGTH]

    trimmed_prefix = safe_prefix[:budget].rstrip("-.")
    if not trimmed_prefix:
        return session_hash[:MAX_INTERFACE_NAME_LENGTH]
    return f"{trimmed_prefix}-{session_hash}"


def bring_up(config_path: Path) -> dict[str, Any]:
    if _is_windows():
        return _bring_up_windows(config_path)
    return _bring_up_linux(config_path)


def bring_down(config_path: Path) -> dict[str, Any]:
    if _is_windows():
        return _bring_down_windows(config_path)
    return _bring_down_linux(config_path)


def _bring_up_linux(config_path: Path) -> dict[str, Any]:
    wg_quick_bin = _resolve_binary("wg-quick")
    try:
        completed = subprocess.run(
            [wg_quick_bin, "up", str(config_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalAppError(
            step="wireguard.up",
            code="wireguard_up_failed",
            message="Failed to start the buyer WireGuard tunnel.",
            hint="Run the buyer client with enough privileges for `wg-quick up` and retry.",
            details={"config_path": str(config_path), "exception": str(exc)},
            status_code=502,
        ) from exc
    if completed.returncode != 0:
        raise LocalAppError(
            step="wireguard.up",
            code="wireguard_up_failed",
            message="`wg-quick up` failed for the buyer runtime session.",
            hint="Check sudo/root privileges and confirm the WireGuard kernel tools are available.",
            details={
                "config_path": str(config_path),
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            },
            status_code=502,
        )
    return {
        "status": "up",
        "config_path": str(config_path),
        "interface_name": config_path.stem,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _bring_down_linux(config_path: Path) -> dict[str, Any]:
    wg_quick_bin = _resolve_binary("wg-quick")
    try:
        completed = subprocess.run(
            [wg_quick_bin, "down", str(config_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalAppError(
            step="wireguard.down",
            code="wireguard_down_failed",
            message="Failed to stop the buyer WireGuard tunnel.",
            hint="Stop the WireGuard tunnel manually and retry.",
            details={"config_path": str(config_path), "exception": str(exc)},
            status_code=502,
        ) from exc
    if completed.returncode != 0:
        raise LocalAppError(
            step="wireguard.down",
            code="wireguard_down_failed",
            message="`wg-quick down` failed for the buyer runtime session.",
            hint="Stop the tunnel manually if it is still active, then retry.",
            details={
                "config_path": str(config_path),
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            },
            status_code=502,
        )
    return {
        "status": "down",
        "config_path": str(config_path),
        "interface_name": config_path.stem,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _bring_up_windows(config_path: Path) -> dict[str, Any]:
    wireguard_exe = _resolve_wireguard_binary()
    interface_name = config_path.stem
    try:
        completed = subprocess.run(
            [wireguard_exe, "/installtunnelservice", str(config_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalAppError(
            step="wireguard.up",
            code="wireguard_install_failed",
            message="Failed to install or start the buyer WireGuard tunnel service.",
            hint="Run the buyer client as administrator and confirm the WireGuard Windows client is installed.",
            details={"config_path": str(config_path), "exception": str(exc)},
            status_code=502,
        ) from exc
    probe: dict[str, Any] | None = None
    converged = completed.returncode == 0
    if _windows_tunnel_already_running(completed):
        probe = _windows_probe_tunnel_running(interface_name)
        converged = bool(probe.get("running"))
    elif converged:
        probe = _windows_probe_tunnel_running(interface_name)
        converged = bool(probe.get("running"))
    if not converged:
        raise LocalAppError(
            step="wireguard.up",
            code="wireguard_install_failed",
            message="Failed to install or start the buyer WireGuard tunnel service.",
            hint="Run the buyer client as administrator and confirm the WireGuard Windows client is installed.",
            details={
                "config_path": str(config_path),
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "probe": probe,
            },
            status_code=502,
        )
    return {
        "status": "up",
        "config_path": str(config_path),
        "interface_name": interface_name,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "converged": True,
        "probe": probe,
    }


def _bring_down_windows(config_path: Path) -> dict[str, Any]:
    wireguard_exe = _resolve_wireguard_binary()
    interface_name = config_path.stem
    try:
        completed = subprocess.run(
            [wireguard_exe, "/uninstalltunnelservice", interface_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError as exc:
        raise LocalAppError(
            step="wireguard.down",
            code="wireguard_remove_failed",
            message="Failed to remove the buyer WireGuard tunnel service.",
            hint="Stop the WireGuard tunnel manually and retry.",
            details={"tunnel_name": interface_name, "exception": str(exc)},
            status_code=502,
        ) from exc
    if completed.returncode != 0:
        raise LocalAppError(
            step="wireguard.down",
            code="wireguard_remove_failed",
            message="Failed to remove the buyer WireGuard tunnel service.",
            hint="Stop the WireGuard tunnel manually and retry.",
            details={
                "tunnel_name": interface_name,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            },
            status_code=502,
        )
    return {
        "status": "down",
        "config_path": str(config_path),
        "interface_name": interface_name,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _normalize_client_address(value: Any) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if "/" in cleaned:
        return cleaned
    return f"{cleaned}/32"


def _resolve_wg_binary() -> str:
    candidates = ("wg.exe", "wg") if _is_windows() else ("wg", "wg.exe")
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    if _is_windows():
        default_path = Path(r"C:\Program Files\WireGuard\wg.exe")
        if default_path.exists():
            return str(default_path)
    raise LocalAppError(
        step="wireguard.binary",
        code="wg_binary_missing",
        message="`wg` was not found on this machine.",
        hint=_wireguard_install_hint("wg"),
        status_code=500,
    )


def _resolve_wireguard_binary() -> str:
    for candidate in ("wireguard.exe", "wireguard"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    if _is_windows():
        default_path = Path(r"C:\Program Files\WireGuard\wireguard.exe")
        if default_path.exists():
            return str(default_path)
    raise LocalAppError(
        step="wireguard.binary",
        code="wireguard_binary_missing",
        message="`wireguard` was not found on this machine.",
        hint=_wireguard_install_hint("wireguard"),
        status_code=500,
    )


def _resolve_binary(name: str) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise LocalAppError(
        step="wireguard.binary",
        code=f"{name}_missing",
        message=f"`{name}` was not found on this machine.",
        hint=_wireguard_install_hint(name),
        status_code=500,
    )


def _wireguard_install_hint(name: str) -> str:
    if _is_windows():
        if name in {"wg", "wireguard"}:
            return "Install the WireGuard Windows client and ensure `wg.exe` / `wireguard.exe` are available."
        return "Install the required Windows WireGuard tooling and retry."
    return "Install the Linux WireGuard tooling before using the buyer runtime session."


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _windows_tunnel_already_running(completed: subprocess.CompletedProcess[str]) -> bool:
    details = "\n".join(part.strip() for part in [completed.stdout, completed.stderr] if part and part.strip()).lower()
    return "already installed and running" in details


def _windows_probe_tunnel_running(interface_name: str, attempts: int = 3, delay_seconds: float = 1.0) -> dict[str, Any]:
    last_probe: dict[str, Any] = {
        "interface_name": interface_name,
        "service_name": _windows_tunnel_service_name(interface_name),
        "service_status": "unknown",
        "wg_show_ok": False,
        "wg_show_stdout": "",
        "wg_show_stderr": "",
        "running": False,
    }
    for attempt in range(1, attempts + 1):
        service_status = _windows_get_service_status(interface_name)
        wg_show = _windows_show_interface(interface_name)
        last_probe = {
            "interface_name": interface_name,
            "service_name": _windows_tunnel_service_name(interface_name),
            "service_status": service_status,
            "wg_show_ok": wg_show.returncode == 0,
            "wg_show_stdout": wg_show.stdout.strip(),
            "wg_show_stderr": wg_show.stderr.strip(),
            "attempt": attempt,
            "running": service_status.lower() == "running" and wg_show.returncode == 0,
        }
        if last_probe["running"]:
            return last_probe
        if attempt < attempts:
            time.sleep(delay_seconds)
    return last_probe


def _windows_tunnel_service_name(interface_name: str) -> str:
    return f"WireGuardTunnel${interface_name}"


def _windows_get_service_status(interface_name: str) -> str:
    service_name = _windows_tunnel_service_name(interface_name)
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                f"if (Get-Service -Name '{service_name}' -ErrorAction SilentlyContinue) "
                f"{{ Get-Service -Name '{service_name}' | Select-Object -ExpandProperty Status }} "
                "else { 'missing' }"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    status = completed.stdout.strip()
    if status:
        return status
    if completed.returncode != 0 and completed.stderr.strip():
        return f"error:{completed.stderr.strip()}"
    return "missing"


def _windows_show_interface(interface_name: str) -> subprocess.CompletedProcess[str]:
    wg_bin = _resolve_wg_binary()
    return subprocess.run(
        [wg_bin, "show", interface_name],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
