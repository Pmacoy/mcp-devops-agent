"""Runs the incident-response demo end to end, for one role.

    python -m demo.run_incident_demo --role readonly
    python -m demo.run_incident_demo --role operator

This is a SCRIPTED decision loop, not a live model call -- see README.md's
"why scripted, not a live model" section for the reasoning. It follows a
fixed sequence of MCP tool calls that mirrors what a reasonable AI DevOps
agent would do when told "something's wrong with the worker": look at
what's running, find the unhealthy one, read its logs, and then either fix
it (if this session is allowed to) or stop and escalate (if it's not).
Narrating each step as it happens is what makes this read like an agent's
transcript rather than a test script, even though which tools get called
in what order is fixed in advance.

Exit code is 0 if the scenario ended the way it's supposed to for the
given role (denied-and-escalated for readonly, fixed for operator) and 1
otherwise -- so this doubles as a real assertion that the access-control
model actually holds, not just a demo that "ran without crashing".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult

from demo import scenario

REPO_ROOT = Path(__file__).resolve().parent.parent


def _narrate(text: str) -> None:
    print(f"\n[agent] {text}")


def _tool_call(label: str) -> None:
    print(f"  -> calling MCP tool: {label}")


def _content_text(result: CallToolResult) -> str:
    for block in result.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise RuntimeError("tool result had no text content block")


def _content_json(result: CallToolResult):
    return json.loads(_content_text(result))


def _clean_error_text(result: CallToolResult) -> str:
    """FastMCP wraps a raised exception's message as
    'Error executing tool <name>: <message>' -- strip the boilerplate so
    the agent's narration reads like an explanation, not a stack trace."""
    text = _content_text(result)
    if text.startswith("Error executing tool") and ": " in text:
        return text.split(": ", 1)[1]
    return text


async def run_agent(role: str) -> bool:
    """Drives the scripted agent for one role. Returns True if the
    scenario ended the way it should have for that role."""
    env = dict(os.environ)
    env["MCP_ROLE"] = role
    env.setdefault("MCP_COMPOSE_PROJECT", "mcp-devops-demo")
    audit_dir = REPO_ROOT / "var"
    audit_dir.mkdir(parents=True, exist_ok=True)
    env["MCP_AUDIT_LOG"] = str(audit_dir / f"audit-{role}.log")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(REPO_ROOT),
        env=env,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            _narrate(f"connected to the MCP server as role={role!r}. Checking what's running.")
            _tool_call("list_services()")
            services = _content_json(await session.call_tool("list_services", {}))["services"]
            print(json.dumps(services, indent=2))

            unhealthy = [s for s in services if s.get("health") == "unhealthy"]
            if not unhealthy:
                _narrate("everything looks healthy already -- nothing for me to do.")
                return False
            target = unhealthy[0]["service"]

            _narrate(f"'{target}' is unhealthy. Pulling its status and recent logs.")
            _tool_call(f"get_service_status(service={target!r})")
            status = _content_json(
                await session.call_tool("get_service_status", {"service": target})
            )
            print(json.dumps(status, indent=2))

            _tool_call(f"get_service_logs(service={target!r}, tail=10)")
            logs = _content_text(
                await session.call_tool("get_service_logs", {"service": target, "tail": 10})
            )
            for line in logs.strip().splitlines()[-10:]:
                print(f"  {line}")

            _narrate(
                f"'{target}' has no recent heartbeat but its process never exited -- "
                "that pattern means stuck, not crashed. A restart should clear it. "
                "Attempting that now."
            )
            _tool_call(f"restart_service(service={target!r})")
            result = await session.call_tool("restart_service", {"service": target})

            if result.isError:
                _narrate(
                    f"restart_service was refused: {_clean_error_text(result)}\n"
                    "  This session doesn't have the operator role, so I can't take "
                    "that action myself. Stopping here and escalating to a human "
                    "operator instead of trying to work around it."
                )
                return role == "readonly"

            after = _content_json(result)
            _narrate(f"restart succeeded. Status right after: {json.dumps(after)}")
            return role == "operator"


async def main_async(role: str) -> int:
    print(f"=== incident demo -- role={role!r} ===")
    print("Triggering the incident (enqueuing a job that hangs the worker)...")
    scenario.trigger_incident()
    scenario.wait_for_worker_unhealthy()
    print("worker is now unhealthy. Handing off to the agent.")

    ok = await run_agent(role)

    if role == "operator":
        print("\nConfirming the worker actually recovered...")
        scenario.wait_for_worker_healthy()
        print("worker is healthy again.")

    outcome = "PASS" if ok else "FAIL"
    print(f"\n=== scenario outcome for role={role!r}: {outcome} ===")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=["readonly", "operator"], required=True)
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args.role)))


if __name__ == "__main__":
    main()
