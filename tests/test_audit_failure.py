import sqlite3
import unittest
from unittest import mock

import audit_log


class AuditLogFailureTests(unittest.TestCase):
    def test_log_event_warns_on_db_failure(self) -> None:
        with mock.patch.object(
            audit_log.sqlite3, "connect", side_effect=sqlite3.OperationalError("boom")
        ):
            with self.assertLogs("audit_log", level="WARNING") as captured:
                result = audit_log.log_event("action.fail", db_path="/tmp/does-not-matter.db")

        self.assertIsNone(result)
        self.assertTrue(
            any(
                "Failed to initialize audit DB" in line or "Failed to log audit event" in line
                for line in captured.output
            )
        )
