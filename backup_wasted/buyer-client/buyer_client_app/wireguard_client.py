from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from buyer_client_app.errors import LocalAppError


def generate_keypair() -> tuple[str, str]:
    wg_bin = _resolve_wg_binary()
    try:
        private_key = subprocess.run([wg_bin, "genkey"], capture_output=True, text=True, timeout=15, check=True).stdout.strip()
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
            hint="Check that WireGuard is installed and `wg.exe` is available in PATH.",
            details={"exception": str(exc)},
            status_code=500,
        ) from exc
    return private_key, public_key


def write_config(
    *,
    config_path: Path,
    private_key: str,
    profile: dict,
) -> None:
    allowed_ips = profile.get("allowed_ips") or []
    if not private_key or not profile.get("server_public_key") or not profile.get("client_address"):
        raise LocalAppError(
            step="wireguard.config",
            code="wireguard_profile_incomplete",
            message="The buyer WireGuard profile is incomplete.",
            hint="Refresh connect material from the platform runtime session before bringing the tunnel up.",
            details={"profile": profile},
            status_code=409,
        )
    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {profile['client_address']}/32",
        "",
        "[Peer]",
        f"PublicKey = {profile['server_public_key']}",
        f"Endpoint = {profile['endpoint_host']}:{profile['endpoint_port']}",
        f"AllowedIPs = {', '.join(allowed_ips)}",
    ]
    if profile.get("persistent_keepalive") is not None:
        lines.append(f"PersistentKeepalive = {profile['persistent_keepalive']}")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_tunnel(config_path: Path) -> str:
    wireguard_exe = _resolve_wireguard_binary()
    try:
        subprocess.run([wireguard_exe, "/installtunnelservice", str(config_path)], capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise LocalAppError(
            step="wireguard.up",
            code="wireguard_install_failed",
            message="Failed to install or start the buyer WireGuard tunnel service.",
            hint="Run the buyer client as administrator and confirm the WireGuard Windows client is installed.",
            details={"config_path": str(config_path), "exception": str(exc)},
            status_code=502,
        ) from exc
    return config_path.stem


def remove_tunnel(tunnel_name: str) -> None:
    wireguard_exe = _resolve_wireguard_binary()
    try:
        subprocess.run([wireguard_exe, "/uninstalltunnelservice", tunnel_name], capture_output=True, text=True, timeout=30, check=False)
    except OSError as exc:  # noqa: BLE001
        raise LocalAppError(
            step="wireguard.down",
            code="wireguard_remove_failed",
            message="Failed to remove the buyer WireGuard tunnel service.",
            hint="Stop the WireGuard tunnel manually and retry.",
            details={"tunnel_name": tunnel_name, "exception": str(exc)},
            status_code=502,
        ) from exc


def _resolve_wg_binary() -> str:
    for candidate in ("wg.exe", "wg"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    default_path = Path(r"C:\Program Files\WireGuard\wg.exe")
    if default_path.exists():
        return str(default_path)
    raise LocalAppError(
        step="wireguard.binary",
        code="wg_binary_missing",
        message="`wg.exe` was not found on this machine.",
        hint="Install the WireGuard Windows client before creating a buyer runtime session.",
        status_code=500,
    )


def _resolve_wireguard_binary() -> str:
    for candidate in ("wireguard.exe", "wireguard"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    default_path = Path(r"C:\Program Files\WireGuard\wireguard.exe")
    if default_path.exists():
        return str(default_path)
    raise LocalAppError(
        step="wireguard.binary",
        code="wireguard_binary_missing",
        message="`wireguard.exe` was not found on this machine.",
        hint="Install the WireGuard Windows client before enabling the buyer tunnel.",
        status_code=500,
    )
