import os
import sqlite3
import tempfile
import unittest

import audit_log


class AuditLogDatabaseTests(unittest.TestCase):
    def test_init_audit_db_creates_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "audit.db")
            ok = audit_log.init_audit_db(db_path)
            self.assertTrue(ok)

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'"
                ).fetchone()
                self.assertIsNotNone(row)

                cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_events)").fetchall()]
                self.assertEqual(
                    cols,
                    [
                        "id",
                        "ts",
                        "request_id",
                        "actor_type",
                        "actor_id",
                        "action",
                        "direction",
                        "source",
                        "chat_id",
                        "thread_id",
                        "message_id",
                        "payload_json",
                        "result_json",
                        "error",
                        "duration_ms",
                    ],
                )
            finally:
                conn.close()
