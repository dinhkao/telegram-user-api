from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import audit_log


class AuditLogTests(unittest.TestCase):
    def test_new_request_id_is_unique_hex(self) -> None:
        first = audit_log.new_request_id()
        second = audit_log.new_request_id()

        self.assertEqual(len(first), 32)
        self.assertEqual(len(second), 32)
        self.assertNotEqual(first, second)
        int(first, 16)
        int(second, 16)

    def test_redact_payload_redacts_nested_sensitive_keys_and_truncates(self) -> None:
        with mock.patch.dict(os.environ, {"AUDIT_MAX_FIELD_CHARS": "6"}, clear=False):
            payload = {
                "apiKey": "abcdef123456",
                "nested": {
                    "token": "secret-token",
                    "profile": [
                        {"password": "p@ssw0rd"},
                        {"phone": "0909123456"},
                    ],
                },
                "public": "0123456789",
            }

            redacted = audit_log.redact_payload(payload)

        self.assertEqual(redacted["apiKey"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["profile"][0]["password"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["profile"][1]["phone"], "[REDACTED]")
        self.assertTrue(redacted["public"].startswith("012345"))
        self.assertTrue(redacted["public"].endswith("...<truncated>"))
        self.assertEqual(payload["apiKey"], "abcdef123456")

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

    def test_log_event_persists_redacted_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "audit.db")
            audit_log.init_audit_db(db_path)

            row_id = audit_log.log_event(
                "message.send",
                request_id="req-123",
                actor_type="user",
                actor_id=99,
                direction="out",
                source="server",
                chat_id=10,
                thread_id=20,
                message_id=30,
                payload={"authorization": "Bearer secret", "message": "hello"},
                result={"token": "abc", "ok": True},
                error=RuntimeError("boom"),
                duration_ms=12.7,
                db_path=db_path,
            )

            self.assertIsInstance(row_id, int)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM audit_events WHERE id = ?",
                    (row_id,),
                ).fetchone()
            finally:
                conn.close()

            self.assertIsNotNone(row)
            self.assertEqual(row["request_id"], "req-123")
            self.assertEqual(row["actor_type"], "user")
            self.assertEqual(row["actor_id"], "99")
            self.assertEqual(row["action"], "message.send")
            self.assertEqual(row["direction"], "out")
            self.assertEqual(row["source"], "server")
            self.assertEqual(row["chat_id"], 10)
            self.assertEqual(row["thread_id"], 20)
            self.assertEqual(row["message_id"], 30)
            self.assertEqual(row["duration_ms"], 13)

            payload = json.loads(row["payload_json"])
            result = json.loads(row["result_json"])
            self.assertEqual(payload["authorization"], "[REDACTED]")
            self.assertEqual(payload["message"], "hello")
            self.assertEqual(result["token"], "[REDACTED]")
            self.assertEqual(result["ok"], True)
            self.assertIn("RuntimeError", row["error"])
            self.assertIn("boom", row["error"])

    def test_async_log_event_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "audit.db")
            audit_log.init_audit_db(db_path)

            row_id = asyncio.run(
                audit_log.async_log_event(
                    "server.start",
                    actor_type="server",
                    source="boot",
                    payload={"session": "abc123"},
                    db_path=db_path,
                )
            )

            self.assertIsInstance(row_id, int)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT payload_json FROM audit_events WHERE id = ?",
                    (row_id,),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(json.loads(row["payload_json"])["session"], "[REDACTED]")

    def test_log_event_warns_on_db_failure(self) -> None:
        with mock.patch.object(audit_log.sqlite3, "connect", side_effect=sqlite3.OperationalError("boom")):
            with self.assertLogs("audit_log", level="WARNING") as captured:
                result = audit_log.log_event("action.fail", db_path="/tmp/does-not-matter.db")

        self.assertIsNone(result)
        self.assertTrue(any("Failed to initialize audit DB" in line or "Failed to log audit event" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
