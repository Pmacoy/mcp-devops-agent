"""Append-only audit log for every MCP tool call.

This is the "secure context sharing" half of the demo's security model:
whatever an AI agent asks this server to do, and whatever the server
answers, is written down -- one JSON object per line, flushed
immediately -- so a human can reconstruct exactly what an agent looked at
and changed after the fact, independent of whatever the agent itself
reports it did.

The log is append-only by construction (opened with mode "a", never
truncated or rewritten by this module) and every record is timestamped and
tagged with the role the server was running as, so "who could have done
this" is answerable from the log alone.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Where the audit log is written. Overridable so the demo and the test
#: suite can each point it somewhere disposable without stepping on a
#: developer's real log.
AUDIT_LOG_ENV_VAR = "MCP_AUDIT_LOG"
DEFAULT_AUDIT_LOG_PATH = "var/audit.log"


def audit_log_path() -> Path:
    raw = os.environ.get(AUDIT_LOG_ENV_VAR, "").strip()
    return Path(raw) if raw else Path(DEFAULT_AUDIT_LOG_PATH)


@dataclass
class AuditRecord:
    tool: str
    role: str
    arguments: dict[str, Any]
    allowed: bool
    ok: bool | None = None
    error: str | None = None
    result_summary: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_json(self) -> str:
        return json.dumps(
            {
                "timestamp": self.timestamp,
                "role": self.role,
                "tool": self.tool,
                "arguments": self.arguments,
                "allowed": self.allowed,
                "ok": self.ok,
                "error": self.error,
                "result_summary": self.result_summary,
            },
            sort_keys=True,
        )


class AuditLogger:
    """Thread-safe writer for the audit log.

    One process (the MCP server) writes; the demo client and the test
    suite only ever read it back, so contention is not really a concern --
    the lock is here mainly so two tool calls resolved concurrently by the
    MCP framework can't interleave partial lines.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or audit_log_path()
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, record: AuditRecord) -> None:
        line = record.to_json()
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def read_all(self) -> list[dict[str, Any]]:
        """Convenience for tests and the demo client's summary printout."""
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
