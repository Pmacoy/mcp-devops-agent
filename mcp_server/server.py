"""Entrypoint: `python -m mcp_server.server`.

Wires the tools in tools.py into a FastMCP server and runs it over stdio --
the same transport Claude Desktop and most other MCP clients use to launch
a local server as a subprocess. There is no network port here on purpose:
this server is only ever reachable by whatever process spawned it.

The role this server runs as (readonly vs operator, see rbac.py) is fixed
by the MCP_ROLE environment variable *of the process that launches this
one* -- an MCP client's server config, not anything the agent can change
once connected. demo/scenario.py shows both launch configs side by side.
"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from . import runtime, tools

mcp: FastMCP = FastMCP(
    name="devops-agent",
    instructions=(
        "Scoped, audited tools for inspecting and remediating the "
        "mcp-devops-demo target stack (services: api, worker, redis). "
        "Read tools (list_services, get_service_status, get_service_logs, "
        "get_service_stats) are always available. restart_service requires "
        "the operator role; a server running as readonly will refuse it "
        "without touching Docker."
    ),
)

for _tool in (
    tools.list_services,
    tools.get_service_status,
    tools.get_service_logs,
    tools.get_service_stats,
    tools.restart_service,
):
    mcp.tool()(_tool)


def main() -> None:
    # Touch runtime at startup (not just on first tool call) so a
    # misconfigured MCP_ROLE is visible the moment the server launches,
    # rather than surfacing later as a confusing PermissionDeniedError deep in
    # a tool call. This MUST go to stderr, never stdout: stdio transport
    # uses stdout exclusively for the JSON-RPC protocol stream, and a
    # single stray print() there would corrupt it from the client's point
    # of view.
    print(
        f"mcp-devops-agent starting as role={runtime.ROLE.value!r} "
        f"(audit log: {runtime.AUDIT.path})",
        file=sys.stderr,
        flush=True,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
