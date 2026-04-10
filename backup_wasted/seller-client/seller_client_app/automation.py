from __future__ import annotations

from typing import Any, Callable

from seller_client_app.backend import BackendClient
from seller_client_app.config import Settings
from seller_client_app.errors import LocalAppError
from seller_client_app.ubuntu_compute import (
    collect_wireguard_node_status,
    detect_ubuntu_swarm_info,
    detect_ubuntu_swarm_node_ref,
)
from seller_client_app.ubuntu_standard_image import pull_standard_image, verify_standard_image
from seller_client_app.windows_host import run_windows_host_install_and_check
from seller_client_app.ubuntu_compute import bootstrap_ubuntu_compute, join_swarm_from_ubuntu


def sell_my_compute_full_auto(
    *,
    settings: Settings,
    backend_client: BackendClient,
    onboarding_session: dict[str, Any],
    windows_install_and_check: Callable[..., dict[str, Any]] = run_windows_host_install_and_check,
    ubuntu_bootstrap_runner: Callable[..., dict[str, Any]] = bootstrap_ubuntu_compute,
    standard_image_pull_runner: Callable[..., dict[str, Any]] = pull_standard_image,
    standard_image_verify_runner: Callable[..., dict[str, Any]] = verify_standard_image,
    join_runner: Callable[..., dict[str, Any]] = join_swarm_from_ubuntu,
    node_status_runner: Callable[..., dict[str, Any]] = collect_wireguard_node_status,
) -> dict[str, Any]:
    session_id = onboarding_session["session_id"]
    requested_accelerator = onboarding_session.get("requested_accelerator") or "gpu"
    compute_node_id = onboarding_session.get("requested_compute_node_id")
    ubuntu_bootstrap = backend_client.get_ubuntu_bootstrap(session_id)

    windows_report = windows_install_and_check(settings, mode="all")
    ubuntu_report = ubuntu_bootstrap_runner(settings, ubuntu_bootstrap)
    standard_image_pull = standard_image_pull_runner(settings, ubuntu_bootstrap)
    standard_image_verify = standard_image_verify_runner(
        settings,
        ubuntu_bootstrap,
        session_id=session_id,
        requested_accelerator=requested_accelerator,
    )
    join_result = join_runner(settings, ubuntu_bootstrap)
    node_ref = detect_ubuntu_swarm_node_ref(settings)
    swarm_info = detect_ubuntu_swarm_info(settings)
    node_status = node_status_runner(
        settings,
        expected_node_addr=ubuntu_bootstrap["ubuntu_compute_bootstrap"]["expected_node_addr"],
        backend_client=backend_client,
        node_ref=node_ref,
    )
    if not node_status["wireguard_addr_match"]:
        raise LocalAppError(
            step="sell_compute.node_addr",
            code="wireguard_node_addr_mismatch",
            message="Swarm node joined, but NodeAddr is not the expected WireGuard address.",
            hint="Ensure WireGuard is up in Ubuntu and re-run join with the backend-provided advertise/data-path addresses.",
            details={"node_status": node_status},
            status_code=409,
        )
    compute_ready = backend_client.post_compute_ready(
        session_id,
        {
            "node_ref": node_ref,
            "swarm_info": swarm_info,
            "standard_image": standard_image_pull,
            "node_status": node_status,
        },
    )
    if not compute_node_id:
        raise LocalAppError(
            step="sell_compute.claim",
            code="compute_node_id_required",
            message="compute_node_id is required before claiming the seller node.",
            hint="Start onboarding with a predefined compute node id or let Backend issue a recommended one.",
            status_code=422,
        )
    claim_result = backend_client.claim_node(
        node_ref=node_ref,
        onboarding_session_id=session_id,
        compute_node_id=compute_node_id,
        requested_accelerator=requested_accelerator,
    )
    claim_status = backend_client.get_claim_status(node_ref)
    return {
        "status": "seller_compute_ready",
        "windows_install_and_check": windows_report,
        "ubuntu_bootstrap": ubuntu_report,
        "standard_image_pull": standard_image_pull,
        "standard_image_verify": standard_image_verify,
        "join_result": join_result,
        "node_ref": node_ref,
        "node_status": node_status,
        "compute_ready": compute_ready,
        "claim_result": claim_result,
        "claim_status": claim_status,
    }
