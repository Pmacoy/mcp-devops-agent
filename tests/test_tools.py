"""Tests for the guard-decorated tool surface: RBAC + audit wiring, using
a mocked docker_cli so nothing here touches a real Docker daemon."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp_server import runtime, tools
from mcp_server.audit import AuditLogger
from mcp_server.rbac import PermissionDeniedError, Role


class ToolsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._role_patch = mock.patch.object(runtime, "ROLE", Role.READONLY)
        self._role_patch.start()
        self._audit = AuditLogger(path=Path(self._tmpdir.name) / "audit.log")
        self._audit_patch = mock.patch.object(runtime, "AUDIT", self._audit)
        self._audit_patch.start()

    def tearDown(self) -> None:
        self._role_patch.stop()
        self._audit_patch.stop()
        self._tmpdir.cleanup()

    def set_role(self, role: Role) -> None:
        self._role_patch.stop()
        self._role_patch = mock.patch.object(runtime, "ROLE", role)
        self._role_patch.start()


class TestReadTools(ToolsTestCase):
    @mock.patch("mcp_server.tools.docker_cli.list_services")
    def test_list_services_readonly_allowed_and_audited(self, mock_list) -> None:
        mock_list.return_value = []
        result = tools.list_services()
        self.assertEqual(result, {"services": []})
        (entry,) = self._audit.read_all()
        self.assertEqual(entry["tool"], "list_services")
        self.assertTrue(entry["allowed"])
        self.assertTrue(entry["ok"])

    @mock.patch("mcp_server.tools.docker_cli.get_status")
    def test_get_service_status_passes_through_service_arg(self, mock_status) -> None:
        mock_status.return_value = {"service": "worker", "health_status": "unhealthy"}
        result = tools.get_service_status(service="worker")
        mock_status.assert_called_once_with("worker")
        self.assertEqual(result["health_status"], "unhealthy")

    @mock.patch("mcp_server.tools.docker_cli.get_logs")
    def test_get_service_logs_defaults_tail(self, mock_logs) -> None:
        mock_logs.return_value = "line1\nline2\n"
        result = tools.get_service_logs(service="api")
        mock_logs.assert_called_once_with("api", 50)
        self.assertIn("line1", result)


class TestRestartServiceRbac(ToolsTestCase):
    @mock.patch("mcp_server.tools.docker_cli.restart_service")
    def test_readonly_role_is_denied_before_touching_docker(self, mock_restart) -> None:
        self.set_role(Role.READONLY)
        with self.assertRaises(PermissionDeniedError):
            tools.restart_service(service="worker")
        mock_restart.assert_not_called()

        (entry,) = self._audit.read_all()
        self.assertEqual(entry["tool"], "restart_service")
        self.assertFalse(entry["allowed"])
        self.assertFalse(entry["ok"])
        self.assertIsNotNone(entry["error"])

    @mock.patch("mcp_server.tools.docker_cli.restart_service")
    def test_operator_role_is_allowed(self, mock_restart) -> None:
        self.set_role(Role.OPERATOR)
        mock_restart.return_value = {"service": "worker", "health_status": "healthy"}

        result = tools.restart_service(service="worker")

        mock_restart.assert_called_once_with("worker")
        self.assertEqual(result["health_status"], "healthy")

        (entry,) = self._audit.read_all()
        self.assertEqual(entry["tool"], "restart_service")
        self.assertTrue(entry["allowed"])
        self.assertTrue(entry["ok"])

    @mock.patch("mcp_server.tools.docker_cli.restart_service")
    def test_failed_restart_is_audited_as_not_ok_but_allowed(self, mock_restart) -> None:
        self.set_role(Role.OPERATOR)
        mock_restart.side_effect = RuntimeError("docker restart failed")

        with self.assertRaises(RuntimeError):
            tools.restart_service(service="worker")

        (entry,) = self._audit.read_all()
        self.assertTrue(entry["allowed"])
        self.assertFalse(entry["ok"])
        self.assertIn("docker restart failed", entry["error"])


if __name__ == "__main__":
    unittest.main()
