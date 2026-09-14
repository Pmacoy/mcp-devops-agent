"""Thin, deliberately narrow wrapper around the `docker` CLI.

Design choices worth calling out, because they're the actual security
mechanism, not just implementation detail:

1. Every command is scoped with `--filter label=com.docker.compose.project=
   <project>` (see COMPOSE_PROJECT below). This MCP server can *only ever
   see or touch containers belonging to this demo's compose stack* -- not
   the other containers that might be running on the same Docker host. An
   agent driving this server has no way to even discover, let alone act
   on, anything outside that project, regardless of what it asks for.

2. On top of that, every tool that takes a "service" argument validates it
   against ALLOWED_SERVICES and re-derives the actual container from
   Docker's own `com.docker.compose.service` label -- it never uses a
   client-supplied string as a container name directly. That closes off
   the obvious injection angle (a service argument like "api; rm -rf /"
   is never given anywhere near a shell) and means a compromised or
   confused agent can't reach a container it wasn't explicitly told about.

3. We shell out to the `docker` CLI with argument lists (never `shell=True`,
   never a formatted string), so there's no command-injection surface even
   before validation.

This module has no MCP-specific code in it on purpose -- it's testable
(and reusable) on its own.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 -- see _run() below for why
from dataclasses import dataclass
from typing import Any

#: The demo's docker-compose.yml pins `name: mcp-devops-demo` so this
#: matches regardless of what directory compose was run from. Overridable
#: for the test suite.
COMPOSE_PROJECT = os.environ.get("MCP_COMPOSE_PROJECT", "mcp-devops-demo")

#: The only services this server will ever discuss. Anything else -- even
#: a real container name -- is rejected before a single `docker` command
#: is run.
ALLOWED_SERVICES = frozenset({"api", "worker", "redis"})

_PROJECT_FILTER = f"label=com.docker.compose.project={COMPOSE_PROJECT}"
_DOCKER_TIMEOUT_SECONDS = 15


class DockerCliError(RuntimeError):
    """A `docker` invocation failed or returned something we didn't expect."""


class UnknownServiceError(ValueError):
    """A caller asked about a service outside ALLOWED_SERVICES, or one that
    isn't currently part of this compose project."""


@dataclass(frozen=True)
class ServiceSummary:
    service: str
    container: str
    image: str
    state: str
    status: str
    health: str | None


def _run(args: list[str]) -> str:
    # bandit (B603/B607) flags this as a subprocess call with a partial
    # executable path; that's fine here: the executable is the fixed
    # literal "docker", the call is an argument list (never shell=True or
    # a formatted string), and every caller-supplied piece of `args` is
    # either a hardcoded subcommand or a value already validated against
    # ALLOWED_SERVICES / re-derived from Docker's own compose-service label
    # (see resolve_container() above) -- never a raw client string.
    try:
        result = subprocess.run(  # nosec B603,B607
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=_DOCKER_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DockerCliError("the `docker` CLI is not installed/on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise DockerCliError(f"`docker {' '.join(args)}` timed out") from exc

    if result.returncode != 0:
        raise DockerCliError(
            f"`docker {' '.join(args)}` failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _list_raw_containers() -> list[dict[str, Any]]:
    """One dict per container in this compose project, from `docker ps`'s
    own JSON output -- includes stopped/unhealthy containers (-a), which
    is the whole point of a status tool."""
    out = _run(
        [
            "ps",
            "-a",
            "--filter",
            _PROJECT_FILTER,
            "--format",
            "{{json .}}",
        ]
    )
    containers = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            containers.append(json.loads(line))
    return containers


def _service_label(container_name: str) -> str | None:
    out = _run(
        [
            "inspect",
            container_name,
            "--format",
            "{{ index .Config.Labels \"com.docker.compose.service\" }}",
        ]
    )
    label = out.strip()
    return label or None


def resolve_container(service: str) -> str:
    """Map an allow-listed service name to its live container name inside
    this compose project. Raises UnknownServiceError for anything else --
    including a syntactically-valid-looking name that just isn't running.
    """
    if service not in ALLOWED_SERVICES:
        raise UnknownServiceError(
            f"'{service}' is not one of the services this server will discuss: "
            f"{sorted(ALLOWED_SERVICES)}"
        )
    for container in _list_raw_containers():
        name = container.get("Names", "")
        if _service_label(name) == service:
            return name
    raise UnknownServiceError(
        f"service '{service}' is not currently part of the "
        f"'{COMPOSE_PROJECT}' compose project (is the stack up?)"
    )


def list_services() -> list[ServiceSummary]:
    summaries: list[ServiceSummary] = []
    for container in _list_raw_containers():
        name = container.get("Names", "")
        service = _service_label(name) or "unknown"
        if service not in ALLOWED_SERVICES:
            # Scoped by project label already, but a compose project could
            # in principle contain services this server doesn't know
            # about (e.g. someone adds one to the compose file later
            # without updating ALLOWED_SERVICES). Skip rather than lie
            # about it.
            continue
        summaries.append(
            ServiceSummary(
                service=service,
                container=name,
                image=container.get("Image", ""),
                state=container.get("State", ""),
                status=container.get("Status", ""),
                health=_extract_health(container.get("Status", "")),
            )
        )
    return sorted(summaries, key=lambda s: s.service)


def _extract_health(status_text: str) -> str | None:
    """`docker ps`'s Status field embeds health as free text, e.g.
    'Up 2 minutes (healthy)' / 'Up 30 seconds (unhealthy)'. Pull it out so
    callers get a clean field instead of having to regex the same text."""
    if "(healthy)" in status_text:
        return "healthy"
    if "(unhealthy)" in status_text:
        return "unhealthy"
    if "(health: starting)" in status_text:
        return "starting"
    return None


def get_status(service: str) -> dict[str, Any]:
    container = resolve_container(service)
    raw = _run(["inspect", container])
    (data,) = json.loads(raw)
    state = data.get("State", {})
    health = state.get("Health", {})
    return {
        "service": service,
        "container": container,
        "status": state.get("Status"),
        "running": state.get("Running"),
        "started_at": state.get("StartedAt"),
        "restart_count": data.get("RestartCount"),
        "health_status": health.get("Status"),
        "last_health_check": (health.get("Log") or [{}])[-1].get("Output", "").strip()
        if health.get("Log")
        else None,
    }


def get_logs(service: str, tail: int = 50) -> str:
    container = resolve_container(service)
    tail = max(1, min(tail, 500))
    return _run(["logs", "--tail", str(tail), container])


def get_stats(service: str) -> dict[str, Any]:
    container = resolve_container(service)
    raw = _run(
        [
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            container,
        ]
    )
    return json.loads(raw.strip().splitlines()[-1])


def restart_service(service: str) -> dict[str, Any]:
    container = resolve_container(service)
    _run(["restart", container])
    return get_status(service)
