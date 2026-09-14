# mcp-devops-agent

A working demo of the **Model Context Protocol (MCP)** used for AI-assisted
DevOps: an MCP server that exposes a small, scoped, audited set of tools
for inspecting and remediating a real (if small) app stack, plus a
scripted "agent" that drives it through an actual incident from detection
to fix.

This corresponds to catalog entry **p46 -- "MCP-Based Demo (AI DevOps)"**
in the DevOps Study Hub: MCP fundamentals, secure context sharing,
AI-system interactions, and controlled AI access. Every one of those shows
up here as an actual mechanism, not just a slide:

| Concept | Where it lives |
|---|---|
| MCP fundamentals | `mcp_server/server.py` -- a real `FastMCP` server over stdio, the same transport Claude Desktop and most MCP clients use |
| Secure context sharing | `mcp_server/audit.py` -- every tool call, allowed or denied, is written to an append-only audit log |
| AI-system interactions | `mcp_server/tools.py` + `demo/run_incident_demo.py` -- a real MCP client session driving real tool calls against a real Docker stack |
| Controlled AI access | `mcp_server/rbac.py` -- two roles, enforced server-side, fixed at process launch (not negotiable by the connecting agent) |

## The scenario

`target-stack/` is a tiny three-service app: `api` (a health-checked HTTP
service), `worker` (a background job processor), and `redis` (the queue
between them). `demo/scenario.py` enqueues a "poison" job that hangs the
worker -- its process never crashes, it just stops making progress, so its
heartbeat goes stale and Docker marks it `unhealthy`. That's a realistic
incident shape: `docker restart worker` genuinely fixes it, because the
problem is a stuck process, not corrupted state.

`demo/run_incident_demo.py` then plays the part of an AI DevOps agent
connected to the MCP server: it lists services, notices `worker` is
unhealthy, reads its status and recent logs, and decides to restart it --
exactly the sequence a reasonable agent would follow. What happens next
depends on which role the server was launched with:

- **readonly**: `restart_service` is refused before Docker is ever
  touched. The agent explains why and stops, instead of trying to work
  around the refusal.
- **operator**: the restart is allowed, and the demo confirms the worker
  is genuinely healthy again afterward -- not just that the tool call
  "succeeded".

Run both:

```bash
make install
make stack-up
make demo-readonly   # -> refused, worker stays unhealthy (correct)
make stack-down

make stack-up
make demo-operator    # -> restart allowed, worker recovers (correct)
make stack-down
```

or `make demo` to run both back to back. `.github/workflows/ci.yml`'s
`integration` job runs exactly this, for real, on every push -- see
**CI/CD** below.

## Security model

Three mechanisms, each doing one job:

1. **RBAC, fixed at launch** (`mcp_server/rbac.py`, `runtime.py`). Every
   tool declares the minimum role it needs; the server's role is resolved
   once from `MCP_ROLE` when the process starts and never changes for the
   life of that connection. An MCP client picks the role by how it
   launches the server (its own config's `env` block) -- the same
   mechanism real clients like Claude Desktop already use to configure a
   local server. The agent on the other end of the connection has no API
   for requesting more access; the human deciding which config to hand it
   is the actual access-control boundary.

2. **An append-only audit log** (`mcp_server/audit.py`, wired in via the
   `@guarded` decorator in `guard.py`). Every tool call -- allowed or
   denied, succeeded or failed -- is written as one JSON line, timestamped
   and tagged with the role that made it, before the result ever reaches
   the agent. `demo/run_incident_demo.py`'s two runs each leave their own
   `var/audit-<role>.log`; diff them and the readonly run's denied
   `restart_service` call is right there.

3. **A scoped, allow-listed Docker surface** (`mcp_server/docker_cli.py`).
   Every command is filtered to containers in this demo's own compose
   project (`--filter label=com.docker.compose.project=...`), and every
   tool that names a service validates it against a fixed allow-list and
   re-derives the real container from Docker's own service label --
   never from a client-supplied string used directly. An agent driving
   this server cannot discover, let alone touch, anything outside
   `api`/`worker`/`redis`, regardless of what it asks for. Commands are
   run as argument lists, never through a shell, so there's no injection
   surface even before that validation runs.

## Why a scripted agent, not a live model call

`demo/run_incident_demo.py` is a deterministic sequence of MCP tool
calls, not a live call to Claude or any other model. Two reasons:

- **CI has no secrets to leak or bill.** The workflow that proves this
  demo actually works runs on every push, unauthenticated, with no API
  key -- consistent with every other project in this portfolio (no cloud
  credentials, no real costs, `terraform apply` against LocalStack instead
  of AWS elsewhere in the series).
- **The interesting part isn't which model made the call.** It's whether
  the server-side access control and audit trail hold up regardless of
  what's on the other end of the MCP connection -- a real point a scripted
  "worst case, most literal-minded agent" actually demonstrates more
  clearly than a model that might reasonably decide not to push the
  refused action.

The scripted agent still runs the same tool calls a real one would (it's
a real MCP client session, not a mock), and its narration is printed as
it happens so the transcript reads like an agent's reasoning. Pointing
`mcp_server/server.py` at a real model with tool-use (Claude, or anything
else that speaks MCP) instead of `demo/run_incident_demo.py` is a drop-in
swap -- the server doesn't know or care who's driving it.

## Repo layout

```
mcp_server/           the MCP server
  server.py             FastMCP entrypoint (stdio transport)
  tools.py               the 5 tools an agent can call
  rbac.py                Role enum + the require() check
  guard.py                the @guarded decorator: RBAC + audit for every tool
  audit.py                append-only JSONL audit log
  docker_cli.py            scoped `docker` CLI wrapper (no docker-py dependency)
  runtime.py                 process-wide role + audit logger, resolved once

target-stack/          the app the MCP server manages
  docker-compose.yml
  api/                    always-healthy service, just to give list_services more to say
  worker/                 the one that breaks (and gets fixed)

demo/                 the scripted "agent" + incident harness
  scenario.py             triggers the incident, polls for health changes
  run_incident_demo.py      the MCP client session + narration + assertions

tests/                unit tests (mock docker_cli -- no daemon required)
```

## CI/CD

- **`ci.yml`**: `ruff` (lint), `mypy` (types), `pytest` (unit tests against
  a mocked `docker_cli`, no Docker needed), then the `integration` job
  described above -- a real `docker compose up --build`, a real incident,
  a real MCP session over stdio, for both roles, asserting the outcome
  each role should produce.
- **`security.yml`**: `gitleaks` (secrets), `hadolint` (both Dockerfiles),
  `bandit` (the Python that ships, not the tests), a Trivy filesystem
  scan, and dependency review on PRs.
- **`dependabot.yml`**: weekly, 7-day cooldown, across GitHub Actions,
  pip, and both Dockerfiles.

## What a real deployment would add

This is a demo, scoped on purpose -- worth being explicit about what it
deliberately leaves out rather than pretending it's production-ready:

- **More roles and finer scopes.** Two roles (readonly/operator) prove the
  mechanism; a real system would likely scope per-service or per-action
  (e.g., "can restart `worker` but not `api`"), and probably add a
  human-approval step for the operator role rather than granting it for
  an entire session.
- **Transport.** stdio is right for a locally-launched server; a
  server shared across a team would run over `streamable-http` (which
  `mcp.server.fastmcp.FastMCP` also supports) behind real authentication,
  not just a launch-time environment variable.
- **Tamper-evident audit storage.** The audit log here is a local file for
  demo purposes; a real deployment would ship it to storage the agent (and
  ideally the human operator) can't edit after the fact.
