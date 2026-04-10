from __future__ import annotations

from typing import Any

from mcp.server import FastMCP

from seller_client_app.active_codex_session import resolve_active_session_file
from seller_client_app.config import get_settings
from seller_client_app.mcp_server import _invoke_tool, _load_session_context, _tool_descriptors


def _tool_description(name: str) -> str:
    for tool in _tool_descriptors():
        if tool.get("name") == name:
            return str(tool.get("description") or name)
    return name


def _call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    session_file = resolve_active_session_file(settings)
    payload = _load_session_context(str(session_file))
    return _invoke_tool(name, arguments or {}, payload, str(session_file))


mcp = FastMCP(
    name="seller-client-tools",
    instructions=(
        "Local seller onboarding MCP server. "
        "Use list_script_capabilities to discover the canonical AI-facing local script tools, then use the controlled local tools "
        "to inspect onboarding state, prepare machine WireGuard identity, execute guided join, verify manager task execution, "
        "refresh backend truth, and export diagnostics."
    ),
)


@mcp.tool(description=_tool_description("read_onboarding_state"))
def read_onboarding_state() -> dict[str, Any]:
    return _call_tool("read_onboarding_state")


@mcp.tool(description=_tool_description("read_join_material"))
def read_join_material() -> dict[str, Any]:
    return _call_tool("read_join_material")


@mcp.tool(description=_tool_description("read_environment_health"))
def read_environment_health() -> dict[str, Any]:
    return _call_tool("read_environment_health")


@mcp.tool(description=_tool_description("list_script_capabilities"))
def list_script_capabilities() -> dict[str, Any]:
    return _call_tool("list_script_capabilities")


@mcp.tool(description=_tool_description("inspect_environment_health"))
def inspect_environment_health(
    expected_wireguard_ip: str | None = None,
    overlay_sample_count: int = 3,
    overlay_interval_seconds: int = 1,
) -> dict[str, Any]:
    return _call_tool(
        "inspect_environment_health",
        {
            "expected_wireguard_ip": expected_wireguard_ip,
            "overlay_sample_count": overlay_sample_count,
            "overlay_interval_seconds": overlay_interval_seconds,
        },
)


@mcp.tool(description=_tool_description("repair_environment_health"))
def repair_environment_health(
    expected_wireguard_ip: str | None = None,
    overlay_sample_count: int = 3,
    overlay_interval_seconds: int = 1,
) -> dict[str, Any]:
    return _call_tool(
        "repair_environment_health",
        {
            "expected_wireguard_ip": expected_wireguard_ip,
            "overlay_sample_count": overlay_sample_count,
            "overlay_interval_seconds": overlay_interval_seconds,
        },
)


@mcp.tool(description=_tool_description("inspect_overlay_runtime"))
def inspect_overlay_runtime(
    overlay_sample_count: int = 3,
    overlay_interval_seconds: int = 1,
) -> dict[str, Any]:
    return _call_tool(
        "inspect_overlay_runtime",
        {
            "overlay_sample_count": overlay_sample_count,
            "overlay_interval_seconds": overlay_interval_seconds,
        },
)


@mcp.tool(description=_tool_description("inspect_network_path"))
def inspect_network_path(
    expected_wireguard_ip: str | None = None,
    overlay_sample_count: int = 3,
    overlay_interval_seconds: int = 1,
) -> dict[str, Any]:
    return _call_tool(
        "inspect_network_path",
        {
            "expected_wireguard_ip": expected_wireguard_ip,
            "overlay_sample_count": overlay_sample_count,
            "overlay_interval_seconds": overlay_interval_seconds,
        },
)


@mcp.tool(description=_tool_description("prepare_machine_wireguard"))
def prepare_machine_wireguard(
    source_path: str | None = None,
    expected_wireguard_ip: str | None = None,
    overwrite_cache: bool = False,
) -> dict[str, Any]:
    return _call_tool(
        "prepare_machine_wireguard",
        {
            "source_path": source_path,
            "expected_wireguard_ip": expected_wireguard_ip,
            "overwrite_cache": overwrite_cache,
        },
)


@mcp.tool(description=_tool_description("execute_join_workflow"))
def execute_join_workflow(
    join_mode: str = "wireguard",
    advertise_address: str | None = None,
    data_path_address: str | None = None,
    listen_address: str | None = None,
    wireguard_config_path: str | None = None,
) -> dict[str, Any]:
    return _call_tool(
        "execute_join_workflow",
        {
            "join_mode": join_mode,
            "advertise_address": advertise_address,
            "data_path_address": data_path_address,
            "listen_address": listen_address,
            "wireguard_config_path": wireguard_config_path,
        },
)


@mcp.tool(description=_tool_description("execute_guided_join"))
def execute_guided_join(
    join_mode: str = "wireguard",
    expected_wireguard_ip: str | None = None,
    wireguard_config_path: str | None = None,
    overlay_sample_count: int = 2,
    overlay_interval_seconds: int = 1,
    post_join_probe_count: int = 8,
    probe_interval_seconds: int = 1,
    manager_probe_count: int = 4,
    manager_probe_interval_seconds: int = 2,
    task_probe_timeout_seconds: int = 60,
    task_probe_interval_seconds: int = 3,
    task_probe_image: str | None = None,
) -> dict[str, Any]:
    return _call_tool(
        "execute_guided_join",
        {
            "join_mode": join_mode,
            "expected_wireguard_ip": expected_wireguard_ip,
            "wireguard_config_path": wireguard_config_path,
            "overlay_sample_count": overlay_sample_count,
            "overlay_interval_seconds": overlay_interval_seconds,
            "post_join_probe_count": post_join_probe_count,
            "probe_interval_seconds": probe_interval_seconds,
            "manager_probe_count": manager_probe_count,
            "manager_probe_interval_seconds": manager_probe_interval_seconds,
            "task_probe_timeout_seconds": task_probe_timeout_seconds,
            "task_probe_interval_seconds": task_probe_interval_seconds,
            "task_probe_image": task_probe_image,
        },
)


@mcp.tool(description=_tool_description("verify_manager_task"))
def verify_manager_task(
    task_probe_timeout_seconds: int = 60,
    task_probe_interval_seconds: int = 3,
    task_probe_image: str | None = None,
) -> dict[str, Any]:
    return _call_tool(
        "verify_manager_task",
        {
            "task_probe_timeout_seconds": task_probe_timeout_seconds,
            "task_probe_interval_seconds": task_probe_interval_seconds,
            "task_probe_image": task_probe_image,
        },
)


@mcp.tool(description=_tool_description("start_local_service"))
def start_local_service(
    port: int | None = None,
    startup_timeout_seconds: int = 20,
) -> dict[str, Any]:
    return _call_tool(
        "start_local_service",
        {
            "port": port,
            "startup_timeout_seconds": startup_timeout_seconds,
        },
    )


@mcp.tool(description=_tool_description("verify_local_service_content"))
def verify_local_service_content(
    port: int | None = None,
    paths: list[str] | None = None,
    expected_status_code: int = 200,
    expected_substring: str | None = None,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    return _call_tool(
        "verify_local_service_content",
        {
            "port": port,
            "paths": paths,
            "expected_status_code": expected_status_code,
            "expected_substring": expected_substring,
            "timeout_seconds": timeout_seconds,
        },
)


@mcp.tool(description=_tool_description("cleanup_join_state"))
def cleanup_join_state(
    leave_timeout_seconds: int = 25,
    dry_run: bool = False,
    refresh_onboarding_session: bool = True,
    close_onboarding_session: bool = False,
    run_environment_check_after_clear: bool = True,
    expected_wireguard_ip: str | None = None,
    overlay_sample_count: int = 2,
    overlay_interval_seconds: int = 1,
    clear_runtime_evidence: bool = True,
    clear_last_assistant_run: bool = True,
) -> dict[str, Any]:
    return _call_tool(
        "cleanup_join_state",
        {
            "leave_timeout_seconds": leave_timeout_seconds,
            "dry_run": dry_run,
            "refresh_onboarding_session": refresh_onboarding_session,
            "close_onboarding_session": close_onboarding_session,
            "run_environment_check_after_clear": run_environment_check_after_clear,
            "expected_wireguard_ip": expected_wireguard_ip,
            "overlay_sample_count": overlay_sample_count,
            "overlay_interval_seconds": overlay_interval_seconds,
            "clear_runtime_evidence": clear_runtime_evidence,
            "clear_last_assistant_run": clear_last_assistant_run,
        },
)


@mcp.tool(description=_tool_description("stop_local_service_and_cleanup"))
def stop_local_service_and_cleanup(
    port: int | None = None,
    stop_local_service: bool = True,
    leave_timeout_seconds: int = 25,
    dry_run: bool = False,
    refresh_onboarding_session: bool = True,
    close_onboarding_session: bool = False,
    run_environment_check_after_clear: bool = True,
    expected_wireguard_ip: str | None = None,
    overlay_sample_count: int = 2,
    overlay_interval_seconds: int = 1,
    clear_runtime_evidence: bool = True,
    clear_last_assistant_run: bool = True,
) -> dict[str, Any]:
    return _call_tool(
        "stop_local_service_and_cleanup",
        {
            "port": port,
            "stop_local_service": stop_local_service,
            "leave_timeout_seconds": leave_timeout_seconds,
            "dry_run": dry_run,
            "refresh_onboarding_session": refresh_onboarding_session,
            "close_onboarding_session": close_onboarding_session,
            "run_environment_check_after_clear": run_environment_check_after_clear,
            "expected_wireguard_ip": expected_wireguard_ip,
            "overlay_sample_count": overlay_sample_count,
            "overlay_interval_seconds": overlay_interval_seconds,
            "clear_runtime_evidence": clear_runtime_evidence,
            "clear_last_assistant_run": clear_last_assistant_run,
        },
    )


@mcp.tool(description=_tool_description("refresh_onboarding_session"))
def refresh_onboarding_session() -> dict[str, Any]:
    return _call_tool("refresh_onboarding_session")


@mcp.tool(description=_tool_description("run_minimum_tcp_validation"))
def run_minimum_tcp_validation(
    host: str,
    port: int,
    timeout_ms: int = 3000,
    validation_kind: str | None = None,
    source: str | None = None,
    target_label: str | None = None,
) -> dict[str, Any]:
    return _call_tool(
        "run_minimum_tcp_validation",
        {
            "host": host,
            "port": port,
            "timeout_ms": timeout_ms,
            "validation_kind": validation_kind,
            "source": source,
            "target_label": target_label,
        },
    )


@mcp.tool(description=_tool_description("export_diagnostics_bundle"))
def export_diagnostics_bundle() -> dict[str, Any]:
    return _call_tool("export_diagnostics_bundle")


def main() -> None:
    mcp.run("stdio")
