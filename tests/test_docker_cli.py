"""Tests for the pure/validating parts of docker_cli.py -- the bits that
don't need a real Docker daemon. The `docker` CLI calls themselves are
exercised for real by the integration workflow (see
.github/workflows/ci.yml), not here.
"""

from __future__ import annotations

import unittest
from unittest import mock

from mcp_server import docker_cli


class TestExtractHealth(unittest.TestCase):
    def test_healthy(self) -> None:
        self.assertEqual(docker_cli._extract_health("Up 2 minutes (healthy)"), "healthy")

    def test_unhealthy(self) -> None:
        self.assertEqual(docker_cli._extract_health("Up 30 seconds (unhealthy)"), "unhealthy")

    def test_starting(self) -> None:
        self.assertEqual(
            docker_cli._extract_health("Up 3 seconds (health: starting)"), "starting"
        )

    def test_no_healthcheck_configured(self) -> None:
        self.assertIsNone(docker_cli._extract_health("Up 5 minutes"))

    def test_exited(self) -> None:
        self.assertIsNone(docker_cli._extract_health("Exited (1) 2 minutes ago"))


class TestResolveContainerValidation(unittest.TestCase):
    def test_rejects_service_outside_allowlist_without_calling_docker(self) -> None:
        with mock.patch("mcp_server.docker_cli._list_raw_containers") as mock_list:
            with self.assertRaises(docker_cli.UnknownServiceError):
                docker_cli.resolve_container("some-other-container-on-the-host")
            mock_list.assert_not_called()

    def test_rejects_allowlisted_service_not_currently_running(self) -> None:
        with mock.patch("mcp_server.docker_cli._list_raw_containers", return_value=[]):
            with self.assertRaises(docker_cli.UnknownServiceError):
                docker_cli.resolve_container("worker")

    def test_resolves_allowlisted_running_service(self) -> None:
        with mock.patch(
            "mcp_server.docker_cli._list_raw_containers",
            return_value=[{"Names": "mcp-devops-demo-worker-1"}],
        ), mock.patch("mcp_server.docker_cli._service_label", return_value="worker"):
            self.assertEqual(
                docker_cli.resolve_container("worker"), "mcp-devops-demo-worker-1"
            )


class TestListServicesFiltersToAllowlist(unittest.TestCase):
    def test_skips_containers_whose_service_label_is_unrecognized(self) -> None:
        containers = [
            {"Names": "mcp-devops-demo-worker-1", "Image": "w", "State": "running", "Status": "Up"},
            {
                "Names": "mcp-devops-demo-mystery-1",
                "Image": "m",
                "State": "running",
                "Status": "Up",
            },
        ]
        with mock.patch(
            "mcp_server.docker_cli._list_raw_containers", return_value=containers
        ), mock.patch(
            "mcp_server.docker_cli._service_label",
            side_effect=lambda name: "worker" if "worker" in name else "mystery",
        ):
            services = docker_cli.list_services()
        self.assertEqual([s.service for s in services], ["worker"])


if __name__ == "__main__":
    unittest.main()
