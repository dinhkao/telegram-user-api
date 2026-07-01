"""Characterization tests for order_store — the order-domain heart.

Locks in CURRENT behavior of the JSON-blob order store so later refactors
(typed model, transactions, column promotion) can't silently change it. Uses a
temp SQLite DB mirroring the shared `orders` schema; every store function takes
an explicit `conn`, so no globals are patched.
"""
from __future__ import annotations

import sqlite3
import unittest

from order_store import (
    _create_order,
    _save_order,
    _update_order_json_field,
    get_order_by_thread_id,
    get_order_json,
    set_task_status,
    clear_task_status,
    set_order_flag,
    save_order_invoice,
    delete_order,
)
from order_store.tasks import _all_steps_done
from order_store.schema import transaction

# Base columns only — the two GENERATED virtual columns in prod are derived and
# never written by Python, so they are irrelevant to these tests.
_ORDERS_DDL = """
CREATE TABLE orders (
    firebase_key TEXT PRIMARY KEY,
    thread_id    INTEGER UNIQUE,
    channel_id   INTEGER,
    message_id   INTEGER,
    json         TEXT NOT NULL,
    updated_at   INTEGER NOT NULL,
    deleted_at   INTEGER
)
"""

THREAD = 555
FKEY = "fk-555"


def _new_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)  # mirror prod autocommit
    conn.row_factory = sqlite3.Row
    conn.execute(_ORDERS_DDL)
    return conn


class OrderStoreCharacterization(unittest.TestCase):
    def setUp(self):
        self.conn = _new_conn()
        ok = _create_order(self.conn, FKEY, THREAD, 111, 222, {"khach_hang": "Anh Tú", "invoice": []})
        self.assertTrue(ok)

    def tearDown(self):
        self.conn.close()

    def test_create_and_get_roundtrip_preserves_unicode(self):
        order = get_order_by_thread_id(self.conn, THREAD)
        self.assertIsNotNone(order)
        self.assertEqual(order["khach_hang"], "Anh Tú")
        self.assertIn("updated_at", order)

    def test_get_missing_returns_none(self):
        self.assertIsNone(get_order_by_thread_id(self.conn, 999999))

    def test_save_order_overwrites_blob(self):
        order = get_order_by_thread_id(self.conn, THREAD)
        order["note"] = "giao gấp"
        self.assertTrue(_save_order(self.conn, THREAD, order))
        self.assertEqual(get_order_by_thread_id(self.conn, THREAD)["note"], "giao gấp")

    def test_update_json_field_with_number_and_dict(self):
        # Numbers and dict/list values work (dict/list get json.dumps'd first).
        self.assertTrue(_update_order_json_field(self.conn, THREAD, "$.priority", 3))
        self.assertTrue(_update_order_json_field(self.conn, THREAD, "$.meta", {"a": 1}))
        order = get_order_by_thread_id(self.conn, THREAD)
        self.assertEqual(order["priority"], 3)
        self.assertEqual(order["meta"], {"a": 1})

    def test_update_json_field_bare_string_now_works(self):
        # Regression: bare strings used to fail (json('VIP') is malformed JSON),
        # silently dropping writes like $.customer_name. Now fixed.
        self.assertTrue(_update_order_json_field(self.conn, THREAD, "$.customer_name", "Anh Tú"))
        self.assertEqual(get_order_by_thread_id(self.conn, THREAD)["customer_name"], "Anh Tú")
        # unicode-safe round-trip
        self.assertTrue(_update_order_json_field(self.conn, THREAD, "$.tag", "Ưu tiên"))
        self.assertEqual(get_order_by_thread_id(self.conn, THREAD)["tag"], "Ưu tiên")

    def test_set_task_status_marks_done_and_mirror_field(self):
        ok = set_task_status(self.conn, THREAD, "soan_hang", user_id=42)
        self.assertTrue(ok)
        order = get_order_by_thread_id(self.conn, THREAD)
        ts = order["task_status"]["soan_hang"]
        self.assertTrue(ts["done"])
        self.assertEqual(ts["by"], 42)
        self.assertFalse(ts["skip"])
        self.assertTrue(order["soan"])          # MIRROR_FIELDS soan_hang -> soan
        self.assertEqual(order["flow_version"], 2)

    def test_set_task_status_skip(self):
        set_task_status(self.conn, THREAD, "nop_tien", user_id=1, skip=True, done=False)
        ts = get_order_by_thread_id(self.conn, THREAD)["task_status"]["nop_tien"]
        self.assertTrue(ts["skip"])
        self.assertFalse(ts["done"])

    def test_set_task_status_missing_order_returns_false(self):
        self.assertFalse(set_task_status(self.conn, 999999, "soan_hang", user_id=1))

    def test_clear_task_status_removes_task_and_unsets_mirror(self):
        set_task_status(self.conn, THREAD, "giao_hang", user_id=7)
        self.assertTrue(clear_task_status(self.conn, THREAD, "giao_hang", user_id=7))
        order = get_order_by_thread_id(self.conn, THREAD)
        self.assertNotIn("giao_hang", order.get("task_status", {}))
        self.assertFalse(order["giao"])

    def test_all_steps_done_predicate(self):
        done = {s: {"done": True} for s in ["ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"]}
        self.assertTrue(_all_steps_done(done))
        done["nhan_tien"] = {"done": False, "skip": True}   # skip counts as satisfied
        self.assertTrue(_all_steps_done(done))
        done["ban_hd"] = {"done": False}
        self.assertFalse(_all_steps_done(done))

    def test_set_order_flag_roundtrip(self):
        ok, _msg = set_order_flag(self.conn, THREAD, "urgent", True)
        self.assertTrue(ok)
        self.assertTrue(get_order_by_thread_id(self.conn, THREAD)["urgent"])

    def test_save_order_invoice(self):
        inv = [{"ma": "SP1", "sl": 2}, {"ma": "SP2", "sl": 1}]
        ok, _msg = save_order_invoice(self.conn, THREAD, inv)
        self.assertTrue(ok)
        self.assertEqual(get_order_json(self.conn, THREAD)["invoice"], inv)

    # --- transaction() helper (Phase 1 race fix) ---

    def test_transaction_commits_and_leaves_no_open_tx(self):
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE orders SET json = json_set(json, '$.x', 1) WHERE thread_id = ?", (THREAD,)
            )
        self.assertFalse(self.conn.in_transaction)          # committed, not left open
        self.assertEqual(get_order_by_thread_id(self.conn, THREAD)["x"], 1)

    def test_transaction_rolls_back_on_exception(self):
        before = get_order_by_thread_id(self.conn, THREAD)
        with self.assertRaises(RuntimeError):
            with transaction(self.conn):
                self.conn.execute(
                    "UPDATE orders SET json = json_set(json, '$.x', 99) WHERE thread_id = ?", (THREAD,)
                )
                raise RuntimeError("boom")
        self.assertFalse(self.conn.in_transaction)
        self.assertEqual(get_order_by_thread_id(self.conn, THREAD), before)   # unchanged

    def test_transaction_reentrant_noop(self):
        with transaction(self.conn):
            with transaction(self.conn):                     # nested = passthrough, no error
                self.conn.execute(
                    "UPDATE orders SET json = json_set(json, '$.y', 2) WHERE thread_id = ?", (THREAD,)
                )
        self.assertEqual(get_order_by_thread_id(self.conn, THREAD)["y"], 2)

    def test_set_task_status_does_not_leak_transaction(self):
        set_task_status(self.conn, THREAD, "soan_hang", user_id=1)
        self.assertFalse(self.conn.in_transaction)           # committed cleanly

    def test_delete_order_soft_deletes(self):
        ok, _msg = delete_order(self.conn, THREAD)
        self.assertTrue(ok)
        # soft delete: hidden when include_deleted=False, still present otherwise
        self.assertIsNone(get_order_by_thread_id(self.conn, THREAD, include_deleted=False))
        self.assertIsNotNone(get_order_by_thread_id(self.conn, THREAD, include_deleted=True))


if __name__ == "__main__":
    unittest.main()
