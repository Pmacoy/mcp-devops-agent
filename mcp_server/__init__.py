"""MCP server exposing scoped, audited DevOps tools for an AI agent.

This package is the "server" half of the demo: it speaks the Model Context
Protocol over stdio and exposes a small, deliberately narrow set of tools
for inspecting and (in the operator role only) remediating the services in
../target-stack. See README.md for the security model.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
