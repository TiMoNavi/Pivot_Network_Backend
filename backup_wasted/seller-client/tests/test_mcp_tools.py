from seller_client_app.mcp_server import _tool_descriptors


def test_mcp_tool_descriptors_include_full_auto_compute_flow() -> None:
    names = {tool["name"] for tool in _tool_descriptors()}

    assert "install_windows_host" in names
    assert "pull_swarm_standard_image" in names
    assert "verify_swarm_standard_image" in names
    assert "join_swarm_from_ubuntu_host" in names
    assert "show_wireguard_node_status" in names
    assert "sell_my_compute_full_auto" in names
    assert "run_swarm_join" not in names
    assert "scan_env" not in names
