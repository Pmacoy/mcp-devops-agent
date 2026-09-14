from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mcp_server.audit import AuditLogger, AuditRecord


class TestAuditLogger(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self._tmpdir.name) / "audit.log"
        self.logger = AuditLogger(path=self.log_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_read_all_on_missing_file_returns_empty(self) -> None:
        self.assertEqual(self.logger.read_all(), [])

    def test_record_is_appended_and_round_trips(self) -> None:
        self.logger.record(
            AuditRecord(
                tool="list_services",
                role="readonly",
                arguments={},
                allowed=True,
                ok=True,
                result_summary="[]",
            )
        )
        entries = self.logger.read_all()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["tool"], "list_services")
        self.assertEqual(entries[0]["role"], "readonly")
        self.assertTrue(entries[0]["allowed"])
        self.assertTrue(entries[0]["ok"])
        self.assertIn("timestamp", entries[0])

    def test_multiple_records_append_in_order(self) -> None:
        for tool in ("list_services", "get_service_status", "restart_service"):
            self.logger.record(
                AuditRecord(tool=tool, role="operator", arguments={}, allowed=True)
            )
        entries = self.logger.read_all()
        self.assertEqual([e["tool"] for e in entries], list(("list_services", "get_service_status", "restart_service")))

    def test_denied_call_is_recorded_with_error_and_not_ok(self) -> None:
        self.logger.record(
            AuditRecord(
                tool="restart_service",
                role="readonly",
                arguments={"service": "worker"},
                allowed=False,
                ok=False,
                error="requires role 'operator'",
            )
        )
        (entry,) = self.logger.read_all()
        self.assertFalse(entry["allowed"])
        self.assertFalse(entry["ok"])
        self.assertIn("operator", entry["error"])

    def test_log_file_is_created_under_missing_parent_dirs(self) -> None:
        nested = Path(self._tmpdir.name) / "a" / "b" / "c" / "audit.log"
        logger = AuditLogger(path=nested)
        logger.record(AuditRecord(tool="x", role="readonly", arguments={}, allowed=True))
        self.assertTrue(nested.exists())


if __name__ == "__main__":
    unittest.main()
