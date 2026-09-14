"""Role-based access control for MCP tools.

This is the "controlled AI access" half of the demo's security model: every
tool the server exposes is tagged with the minimum Role required to call
it, and every call is checked against the role the server process was
started with -- there is no way for a client to escalate its own role
mid-session, because the role is fixed at process start (see server.py),
not negotiated over the protocol.

Two roles are enough to demonstrate the pattern without over-engineering a
demo:

- READONLY can only observe (list services, read status/logs/stats).
- OPERATOR can additionally take a remediation action (restart a service).

A real deployment would likely have more roles and finer-grained scopes
(per-service, per-action), but the mechanism -- a declared minimum role per
tool, enforced server-side, independent of what the calling agent claims
about itself -- is the same at any scale.
"""

from __future__ import annotations

import os
from enum import Enum


class Role(str, Enum):
    """Trust level granted to whoever is driving this MCP server."""

    READONLY = "readonly"
    OPERATOR = "operator"

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]


_ROLE_RANK: dict[Role, int] = {
    Role.READONLY: 0,
    Role.OPERATOR: 1,
}

#: Environment variable an MCP client sets (in its server launch config) to
#: pick which role this server process runs as. This mirrors how real MCP
#: clients configure servers -- e.g. Claude Desktop's config.json sets an
#: "env" block per server entry -- so granting an agent more access is a
#: config change the *human* makes, not something the agent can negotiate
#: for itself over the protocol.
ROLE_ENV_VAR = "MCP_ROLE"


class PermissionDenied(PermissionError):
    """Raised when the server's current role can't call a given tool."""

    def __init__(self, tool_name: str, required: Role, actual: Role) -> None:
        self.tool_name = tool_name
        self.required = required
        self.actual = actual
        super().__init__(
            f"tool '{tool_name}' requires role '{required.value}' or higher, "
            f"but this server is running as '{actual.value}'"
        )


def role_from_env(default: Role = Role.READONLY) -> Role:
    """Resolve the server's role from MCP_ROLE, defaulting to the least
    privilege available if it's unset or unrecognized -- an MCP server that
    fails to configure a role correctly should fail *closed*, not open.
    """
    raw = os.environ.get(ROLE_ENV_VAR, "").strip().lower()
    if not raw:
        return default
    try:
        return Role(raw)
    except ValueError:
        return default


def require(current: Role, minimum: Role, tool_name: str) -> None:
    """Raise PermissionDenied unless `current` meets or exceeds `minimum`."""
    if current.rank < minimum.rank:
        raise PermissionDenied(tool_name, minimum, current)
