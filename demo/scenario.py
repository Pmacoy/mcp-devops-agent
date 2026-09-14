"""Sets up the incident this demo's agent investigates and (maybe) fixes.

This module talks to Docker directly, reusing mcp_server.docker_cli's
already-scoped helpers for convenience -- but it is test/demo harness
code, not an MCP tool. Keeping that boundary explicit matters: the agent
in run_incident_demo.py should only ever see and change the world through
the tools in mcp_server/tools.py, exactly like a real MCP client would,
never by reaching around them.
"""

from __future__ import annotations

import subprocess  # nosec B404 -- see _redis_cli() below for why
import time

from mcp_server import docker_cli

POLL_INTERVAL_SECONDS = 1
INCIDENT_TIMEOUT_SECONDS = 45
REDIS_TIMEOUT_SECONDS = 10


class ScenarioError(RuntimeError):
    """The demo stack didn't behave the way the scenario expects."""


def trigger_incident() -> None:
    """Enqueue a normal job followed by the poison job that hangs the
    worker -- see target-stack/worker/worker.py for what happens to it."""
    redis_container = docker_cli.resolve_container("redis")
    _redis_cli(redis_container, ["RPUSH", "jobs", "warm-up-job", "poison"])


def wait_for_worker_unhealthy(timeout: int = INCIDENT_TIMEOUT_SECONDS) -> None:
    _wait_for_health("worker", "unhealthy", timeout)


def wait_for_worker_healthy(timeout: int = INCIDENT_TIMEOUT_SECONDS) -> None:
    _wait_for_health("worker", "healthy", timeout)


def _wait_for_health(service: str, target: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    last_seen: str | None = None
    while time.monotonic() < deadline:
        status = docker_cli.get_status(service)
        last_seen = status.get("health_status")
        if last_seen == target:
            return
        time.sleep(POLL_INTERVAL_SECONDS)
    raise ScenarioError(
        f"timed out after {timeout}s waiting for '{service}' health to "
        f"reach {target!r} (last seen: {last_seen!r})"
    )


def _redis_cli(container: str, args: list[str]) -> None:
    # bandit (B603/B607) flags this the same way as mcp_server/docker_cli.py's
    # _run(): fixed "docker" executable, an argument list (never shell=True),
    # and `container` always comes from docker_cli.resolve_container()
    # (allow-listed + re-derived from Docker's own labels), never straight
    # from a caller-supplied string.
    result = subprocess.run(  # nosec B603,B607
        ["docker", "exec", container, "redis-cli", *args],
        capture_output=True,
        text=True,
        timeout=REDIS_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise ScenarioError(f"redis-cli {' '.join(args)} failed: {result.stderr.strip()}")
