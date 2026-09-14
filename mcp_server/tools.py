"""The tools this MCP server exposes to an AI agent.

Every function here is a tool: its name, parameter types, and docstring
become the tool's name/schema/description that an MCP client shows the
model, so keep signatures and docstrings accurate -- they're not just
comments, they're the interface the agent reasons from.

Four read tools are available to any role; the one write tool
(restart_service) requires the operator role. See rbac.py and guard.py for
how that's enforced, and docker_cli.py for what these actually do.
"""

from __future__ import annotations

from typing import Any

from . import docker_cli
from .guard import guarded
from .rbac import Role


@guarded(Role.READONLY)
def list_services() -> dict[str, Any]:
    """List every service in the demo stack (api, worker, redis) with its
    current container state and health status.

    Returns a single object -- {"services": [...]} -- rather than a bare
    list. FastMCP serializes a list-typed tool result as one content block
    *per list item* rather than one block for the whole list, which would
    silently drop everything but the first service (or, with zero
    services, produce no content block at all). Wrapping it in a dict
    keeps this tool's result a single well-formed JSON document, matching
    every other tool here.
    """
    return {"services": [vars(s) for s in docker_cli.list_services()]}


@guarded(Role.READONLY)
def get_service_status(service: str) -> dict[str, Any]:
    """Get detailed status for one service: running state, health, restart
    count, and its most recent health-check output.

    Args:
        service: One of "api", "worker", "redis".
    """
    return docker_cli.get_status(service)


@guarded(Role.READONLY)
def get_service_logs(service: str, tail: int = 50) -> str:
    """Tail the most recent log lines for one service.

    Args:
        service: One of "api", "worker", "redis".
        tail: Number of lines to return from the end of the log (1-500).
    """
    return docker_cli.get_logs(service, tail)


@guarded(Role.READONLY)
def get_service_stats(service: str) -> dict[str, Any]:
    """Get a live CPU/memory usage snapshot for one service.

    Args:
        service: One of "api", "worker", "redis".
    """
    return docker_cli.get_stats(service)


@guarded(Role.OPERATOR)
def restart_service(service: str) -> dict[str, Any]:
    """Restart one service and return its status afterward. Requires the
    operator role -- a server running as readonly will refuse this before
    touching Docker at all.

    Args:
        service: One of "api", "worker", "redis".
    """
    return docker_cli.restart_service(service)
