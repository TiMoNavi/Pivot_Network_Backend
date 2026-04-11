from __future__ import annotations

try:
    from mcp.server import FastMCP  # noqa: F401
except ModuleNotFoundError:
    FastMCP = None  # type: ignore[assignment]


def main() -> None:
    if FastMCP is None:
        from buyer_client_app.mcp_server import main as stdio_main

        stdio_main()
        return

    from buyer_client_app.mcp_server import main as stdio_main

    # The repo runtime does not guarantee the external `mcp` package is installed.
    # Keep the entrypoint stable and fall back to the self-contained stdio MCP server.
    stdio_main()
