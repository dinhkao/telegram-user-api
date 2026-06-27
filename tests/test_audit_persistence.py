from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest

import audit_log


class AuditLogPersistenceTests(unittest.TestCase):
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
                row = conn.execute("SELECT * FROM audit_events WHERE id = ?", (row_id,)).fetchone()
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
