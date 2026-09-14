"""Process-wide state, resolved once at import time.

An MCP server talking over stdio is spawned fresh per client connection
(see README.md's "how the demo runs" section), so "once at import time"
really does mean "once per session" here -- there is no long-lived server
process whose role could drift or be reconfigured mid-flight. Restarting
the process with a different MCP_ROLE is the only way to change what an
agent is allowed to do, and that's a deliberate property, not a
limitation: the human operator controls trust by choosing which launch
config (see demo/scenario.py) to hand an agent, not the agent itself.
"""

from __future__ import annotations

from .audit import AuditLogger
from .rbac import Role, role_from_env

ROLE: Role = role_from_env()
AUDIT = AuditLogger()
