from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from seller_client_app.config import Settings
from seller_client_app.errors import LocalAppError

if TYPE_CHECKING:
    from seller_client_app.backend import BackendClient

CHECK_METADATA: dict[str, dict[str, Any]] = {
    "ubuntu_distro": {
        "title": "Ubuntu 发行版",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "seller compute 必须运行在目标 Ubuntu WSL 发行版中。",
    },
    "ubuntu_apt": {
        "title": "Ubuntu apt",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "Ubuntu compute 需要 apt 来安装 docker.io 和 wireguard-tools。",
    },
    "ubuntu_docker_cli": {
        "title": "Ubuntu Docker CLI",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "seller runtime image 必须通过 Ubuntu Docker Engine 构建。",
    },
    "ubuntu_dockerd": {
        "title": "Ubuntu dockerd",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "Ubuntu compute 需要原生 dockerd，不能依赖 Windows Docker Desktop。",
    },
    "ubuntu_wireguard": {
        "title": "Ubuntu WireGuard",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "Ubuntu compute 必须具备 wireguard-tools 与独立 peer 能力。",
    },
    "ubuntu_wireguard_peer": {
        "title": "Ubuntu WireGuard Peer 状态",
        "category": "ubuntu_compute",
        "blocking": False,
        "hint": "用于确认 Ubuntu compute peer 当前是否已经在目标接口上运行。",
    },
    "ubuntu_workspace_root": {
        "title": "Ubuntu 工作目录",
        "category": "ubuntu_compute",
        "blocking": True,
        "hint": "Ubuntu compute 需要稳定可写的 workspace root。",
    },
    "ubuntu_swarm_info": {
        "title": "Ubuntu Swarm 信息",
        "category": "swarm",
        "blocking": False,
        "hint": "用于确认 Ubuntu Docker 是否已加入 Swarm。",
    },
    "ubuntu_swarm_node_addr": {
        "title": "Ubuntu Swarm NodeAddr",
        "category": "swarm",
        "blocking": False,
        "hint": "Joined 后 NodeAddr 应收敛到 Ubuntu WireGuard IP。",
    },
}


def run_ubuntu_shell(settings: Settings, script: str, *, timeout: int = 300) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["wsl", "-d", settings.ubuntu_distribution_name, "--", "bash", "-lc", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr or "").replace("\x00", "").strip()
    return completed.returncode == 0, output


def scan_ubuntu_compute(settings: Settings) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(_check("ubuntu_distro", *_status(run_ubuntu_shell(settings, "true"), "Ubuntu distribution is available.", "Ubuntu distribution is not available.")))
    checks.append(_check("ubuntu_apt", *_status(run_ubuntu_shell(settings, "which apt"), "apt is available.", "apt is not available.")))
    checks.append(_check("ubuntu_docker_cli", *_status(run_ubuntu_shell(settings, "which docker"), "docker CLI is available in Ubuntu.", "docker CLI is missing in Ubuntu.")))
    checks.append(_check("ubuntu_dockerd", *_status(run_ubuntu_shell(settings, "which dockerd"), "dockerd binary is available in Ubuntu.", "dockerd binary is missing in Ubuntu.")))
    checks.append(_check("ubuntu_wireguard", *_status(run_ubuntu_shell(settings, "which wg"), "wg is available in Ubuntu.", "wg is missing in Ubuntu.")))
    wg_peer_ok, wg_peer_output = run_ubuntu_shell(settings, f"wg show {settings.ubuntu_compute_interface_name}")
    checks.append(
        _check(
            "ubuntu_wireguard_peer",
            "pass" if wg_peer_ok else "warn",
            wg_peer_output or f"WireGuard interface {settings.ubuntu_compute_interface_name} is not active.",
        )
    )
    checks.append(
        _check(
            "ubuntu_workspace_root",
            *_status(
                run_ubuntu_shell(
                    settings,
                    f"mkdir -p {settings.ubuntu_workspace_root} && test -d {settings.ubuntu_workspace_root}",
                ),
                f"Ubuntu workspace root is writable: {settings.ubuntu_workspace_root}",
                f"Ubuntu workspace root is not writable: {settings.ubuntu_workspace_root}",
            ),
        )
    )
    docker_info_ok, docker_info_output = run_ubuntu_shell(settings, "docker info --format '{{json .Swarm}}'")
    checks.append(_check("ubuntu_swarm_info", "pass" if docker_info_ok else "warn", docker_info_output or "Ubuntu Docker swarm info unavailable"))
    node_addr_ok, node_addr_output = run_ubuntu_shell(settings, "docker info --format '{{.Swarm.NodeAddr}}'")
    node_addr = node_addr_output.splitlines()[-1].strip() if node_addr_output.strip() else ""
    if node_addr_ok and node_addr:
        status = "pass" if node_addr == settings.ubuntu_swarm_advertise_addr else "warn"
        detail = f"Ubuntu Docker NodeAddr: {node_addr}"
    else:
        status = "warn"
        detail = node_addr_output or "Ubuntu Docker NodeAddr unavailable."
    checks.append(_check("ubuntu_swarm_node_addr", status, detail))
    ubuntu_compute_checks = [item for item in checks if item["category"] == "ubuntu_compute"]
    swarm_checks = [item for item in checks if item["category"] == "swarm"]
    return {
        "distribution_name": settings.ubuntu_distribution_name,
        "summary": _summarize(checks),
        "ubuntu_compute_checks": ubuntu_compute_checks,
        "swarm_checks": swarm_checks,
        "checks": checks,
    }


def bootstrap_ubuntu_compute(settings: Settings, ubuntu_bootstrap: dict[str, Any]) -> dict[str, Any]:
    script = ubuntu_bootstrap["ubuntu_compute_bootstrap"]["bootstrap_script_bash"]
    ok, output = run_ubuntu_shell(settings, script, timeout=900)
    if not ok:
        raise LocalAppError(
            step="ubuntu.bootstrap",
            code="ubuntu_bootstrap_failed",
            message="Failed to bootstrap the Ubuntu compute environment.",
            hint="Check WSL Ubuntu availability, apt access, and package installation output.",
            details={"output": output},
            status_code=502,
        )
    return {"status": "bootstrapped", "output": output}


def sync_context_to_ubuntu(settings: Settings, local_source_path: str, ubuntu_target_path: str | None = None) -> dict[str, Any]:
    ubuntu_target_path = ubuntu_target_path or settings.ubuntu_workspace_root
    source_path = Path(local_source_path)
    if not source_path.exists():
        raise LocalAppError(
            step="ubuntu.sync",
            code="local_context_missing",
            message="The selected local build context does not exist.",
            hint="Choose a valid Windows directory before syncing to Ubuntu.",
            details={"path": str(source_path)},
            status_code=422,
        )
    ok, translated_path = run_ubuntu_shell(settings, f"wslpath -a '{local_source_path}'")
    if not ok:
        raise LocalAppError(
            step="ubuntu.sync",
            code="wslpath_failed",
            message="Failed to translate the Windows path into a WSL path.",
            hint="Ensure the selected build context is on a Windows-accessible drive and retry.",
            details={"path": local_source_path, "output": translated_path},
            status_code=502,
        )
    ubuntu_source = translated_path.splitlines()[-1].strip()
    script = (
        f"mkdir -p '{ubuntu_target_path}' && "
        f"rm -rf '{ubuntu_target_path}/'* && "
        f"cp -a '{ubuntu_source}/.' '{ubuntu_target_path}/'"
    )
    ok, output = run_ubuntu_shell(settings, script, timeout=900)
    if not ok:
        raise LocalAppError(
            step="ubuntu.sync",
            code="ubuntu_context_sync_failed",
            message="Failed to copy the Windows build context into Ubuntu.",
            hint="Check Windows path visibility from WSL and available disk space in Ubuntu.",
            details={"source": ubuntu_source, "target": ubuntu_target_path, "output": output},
            status_code=502,
        )
    return {"status": "synced", "ubuntu_source": ubuntu_source, "ubuntu_target": ubuntu_target_path}


def join_swarm_from_ubuntu(settings: Settings, join_payload: dict[str, Any]) -> dict[str, Any]:
    join = join_payload["ubuntu_compute_bootstrap"]["swarm_join"]
    script = (
        "docker swarm leave --force >/dev/null 2>&1 || true; "
        f"{join['swarm_join_command']}"
    )
    ok, output = run_ubuntu_shell(settings, script, timeout=180)
    if not ok:
        raise LocalAppError(
            step="ubuntu.swarm_join",
            code="ubuntu_swarm_join_failed",
            message="Ubuntu compute failed to join the Swarm cluster.",
            hint="Check WireGuard peer status, manager reachability, and whether dockerd is running in Ubuntu.",
            details={"output": output},
            status_code=502,
        )
    return {"status": "joined", "output": output}


def detect_ubuntu_swarm_node_ref(settings: Settings) -> str:
    ok, output = run_ubuntu_shell(settings, "docker info --format '{{.Swarm.NodeID}}'", timeout=30)
    if not ok or not output.strip():
        raise LocalAppError(
            step="ubuntu.swarm_node",
            code="ubuntu_swarm_node_missing",
            message="Unable to determine the Ubuntu compute swarm node id.",
            hint="Ensure Ubuntu Docker Engine is installed, running, and joined to the Swarm cluster.",
            details={"output": output},
            status_code=502,
        )
    return output.strip().splitlines()[-1]


def detect_ubuntu_swarm_info(settings: Settings) -> dict[str, Any]:
    ok, output = run_ubuntu_shell(settings, "docker info --format '{{json .Swarm}}'", timeout=30)
    if not ok:
        raise LocalAppError(
            step="ubuntu.swarm_info",
            code="ubuntu_swarm_info_failed",
            message="Unable to fetch swarm info from Ubuntu Docker.",
            hint="Check whether dockerd is installed and running inside Ubuntu.",
            details={"output": output},
            status_code=502,
        )
    return {"swarm": output}


def get_ubuntu_swarm_state(settings: Settings) -> dict[str, Any]:
    ok, output = run_ubuntu_shell(settings, "docker info --format '{{json .Swarm}}'", timeout=30)
    if not ok:
        raise LocalAppError(
            step="ubuntu.swarm_state",
            code="ubuntu_swarm_state_failed",
            message="Unable to fetch structured swarm state from Ubuntu Docker.",
            hint="Check whether Ubuntu Docker Engine is installed, running, and already joined to the Swarm cluster.",
            details={"output": output},
            status_code=502,
        )
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise LocalAppError(
            step="ubuntu.swarm_state",
            code="ubuntu_swarm_state_invalid_json",
            message="Ubuntu Docker returned invalid swarm state JSON.",
            hint="Retry after verifying the local Docker daemon is healthy.",
            details={"output": output},
            status_code=502,
        ) from exc


def detect_ubuntu_swarm_node_addr(settings: Settings) -> str:
    ok, output = run_ubuntu_shell(settings, "docker info --format '{{.Swarm.NodeAddr}}'", timeout=30)
    if not ok or not output.strip():
        raise LocalAppError(
            step="ubuntu.swarm_node_addr",
            code="ubuntu_swarm_node_addr_missing",
            message="Unable to determine the Ubuntu Docker Swarm NodeAddr.",
            hint="Ensure Ubuntu Docker Engine is joined to Swarm before checking the node address.",
            details={"output": output},
            status_code=502,
        )
    return output.strip().splitlines()[-1]


def collect_wireguard_node_status(
    settings: Settings,
    *,
    expected_node_addr: str,
    backend_client: "BackendClient | None" = None,
    node_ref: str | None = None,
) -> dict[str, Any]:
    node_ref = node_ref or detect_ubuntu_swarm_node_ref(settings)
    local_node_addr = detect_ubuntu_swarm_node_addr(settings)
    local_swarm_state = get_ubuntu_swarm_state(settings)

    platform_node: dict[str, Any] | None = None
    if backend_client is not None:
        try:
            claim_status = backend_client.get_claim_status(node_ref)
            platform_node = claim_status.get("node")
        except Exception:  # noqa: BLE001
            try:
                for node in backend_client.list_nodes():
                    if node.get("id") == node_ref or node.get("node_ref") == node_ref:
                        platform_node = node
                        break
            except Exception:  # noqa: BLE001
                platform_node = None

    platform_node_addr = platform_node.get("node_addr") if platform_node else None
    platform_match = bool(platform_node_addr) and platform_node_addr == expected_node_addr
    local_match = local_node_addr == expected_node_addr
    return {
        "node_ref": node_ref,
        "expected_node_addr": expected_node_addr,
        "local_node_addr": local_node_addr,
        "local_wireguard_addr_match": local_match,
        "platform_node_addr": platform_node_addr,
        "platform_wireguard_addr_match": platform_match,
        "wireguard_addr_match": local_match and (platform_match if platform_node is not None else True),
        "local_swarm_state": local_swarm_state,
        "platform_node": platform_node,
    }


def _status(result: tuple[bool, str], success_detail: str, fail_detail: str) -> tuple[str, str]:
    ok, output = result
    return ("pass" if ok else "fail", success_detail if ok else (output or fail_detail))


def _check(name: str, status: str, detail: str) -> dict[str, Any]:
    meta = CHECK_METADATA.get(name, {})
    return {
        "name": name,
        "title": meta.get("title", name),
        "category": meta.get("category", "ubuntu_compute"),
        "status": status,
        "blocking": bool(meta.get("blocking", False)),
        "detail": detail,
        "hint": meta.get("hint"),
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
