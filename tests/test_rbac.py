from __future__ import annotations

import unittest
from unittest import mock

from mcp_server.rbac import PermissionDeniedError, Role, require, role_from_env


class TestRoleRank(unittest.TestCase):
    def test_operator_outranks_readonly(self) -> None:
        self.assertGreater(Role.OPERATOR.rank, Role.READONLY.rank)


class TestRoleFromEnv(unittest.TestCase):
    def test_defaults_to_readonly_when_unset(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("MCP_ROLE", None)
            self.assertEqual(role_from_env(default=Role.READONLY), Role.READONLY)

    def test_parses_operator(self) -> None:
        with mock.patch.dict("os.environ", {"MCP_ROLE": "operator"}):
            self.assertEqual(role_from_env(), Role.OPERATOR)

    def test_unrecognized_value_fails_closed_to_readonly(self) -> None:
        with mock.patch.dict("os.environ", {"MCP_ROLE": "super-admin-please"}):
            self.assertEqual(role_from_env(), Role.READONLY)


class TestRequire(unittest.TestCase):
    def test_allows_when_role_meets_minimum(self) -> None:
        require(Role.OPERATOR, Role.READONLY, "some_tool")  # should not raise
        require(Role.OPERATOR, Role.OPERATOR, "some_tool")  # should not raise

    def test_denies_when_role_is_below_minimum(self) -> None:
        with self.assertRaises(PermissionDeniedError) as ctx:
            require(Role.READONLY, Role.OPERATOR, "restart_service")
        self.assertEqual(ctx.exception.tool_name, "restart_service")
        self.assertEqual(ctx.exception.required, Role.OPERATOR)
        self.assertEqual(ctx.exception.actual, Role.READONLY)
        self.assertIn("restart_service", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
