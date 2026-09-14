"""The `@guarded` decorator: the one place RBAC enforcement and audit
logging actually happen for every tool.

Every tool in tools.py goes through this, so there is exactly one code
path that can grant access and exactly one that writes the audit trail --
a new tool can't accidentally skip either by forgetting a check inline.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any, TypeVar

from . import runtime
from .audit import AuditRecord
from .rbac import PermissionDenied, Role, require

F = TypeVar("F", bound=Callable[..., Any])

_MAX_SUMMARY_CHARS = 300


def guarded(minimum_role: Role) -> Callable[[F], F]:
    """Wrap a tool function so that every call is (a) checked against the
    server's current role and (b) recorded to the audit log, win or lose.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tool_name = fn.__name__

            try:
                require(runtime.ROLE, minimum_role, tool_name)
            except PermissionDenied as exc:
                runtime.AUDIT.record(
                    AuditRecord(
                        tool=tool_name,
                        role=runtime.ROLE.value,
                        arguments=kwargs,
                        allowed=False,
                        ok=False,
                        error=str(exc),
                    )
                )
                raise

            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                runtime.AUDIT.record(
                    AuditRecord(
                        tool=tool_name,
                        role=runtime.ROLE.value,
                        arguments=kwargs,
                        allowed=True,
                        ok=False,
                        error=str(exc),
                    )
                )
                raise

            runtime.AUDIT.record(
                AuditRecord(
                    tool=tool_name,
                    role=runtime.ROLE.value,
                    arguments=kwargs,
                    allowed=True,
                    ok=True,
                    result_summary=_summarize(result),
                )
            )
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def _summarize(result: Any) -> str:
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    if len(text) <= _MAX_SUMMARY_CHARS:
        return text
    return text[:_MAX_SUMMARY_CHARS] + "…"
