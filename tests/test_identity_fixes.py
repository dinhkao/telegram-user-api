"""Tests 3 fix danh tính (2026-07-09): thợ SX theo worker_id (đổi tên không tách
lịch sử — cascade rows + blob bang), add_customer key duy nhất (trùng tên không
đè), rename_user cascade việc/bình luận."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from utils.db import get_connection


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)

    def tearDown(self):
        self.conn.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass


class WorkerIdentity(Base):
    def setUp(self):
        super().setUp()
        from product_store import create_products_table, migrate_products_table
        from product_store.schema import _invalidate_products_cache
        from production_store.report_rows import ensure_report_rows_schema
        from production_store.schema import create_production_table, migrate_production_table
        from worker_store import add_worker, ensure_table
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        create_production_table(self.conn)
        migrate_production_table(self.conn)
        ensure_table(self.conn)
        ensure_report_rows_schema(self.conn)
        self.tho = add_worker(self.conn, "Thao")

    def _save_report(self, tid, names):
        from production_store.queries import set_bang, upsert_slip
        upsert_slip(self.conn, tid, date_code="20260709")
        set_bang(self.conn, tid, {
            "product_code": None, "date": "9/7/2026",
            "rows": [{"name": n, "so_gach": 10, "tong_calc": 100} for n in names],
        })

    def test_rows_get_worker_id(self):
        self._save_report(300, ["Thao", "Người Lạ"])
        rows = self.conn.execute(
            "SELECT worker_name, worker_id FROM production_report_rows WHERE thread_id=300 ORDER BY worker_name"
        ).fetchall()
        d = {r[0]: r[1] for r in rows}
        self.assertEqual(d["Thao"], self.tho["id"])
        self.assertIsNone(d["Người Lạ"])   # không bịa danh tính

    def test_rename_worker_cascades_everywhere(self):
        from production_store.report_rows import dashboard, worker_detail
        from worker_store import update_worker
        self._save_report(301, ["Thao"])
        # dòng cổ chưa gán id (giả lập DB trước migration)
        self.conn.execute("UPDATE production_report_rows SET worker_id = NULL WHERE thread_id = 301")
        self._save_report(302, ["Thao"])
        update_worker(self.conn, self.tho["id"], name="Thảo")
        # mirror rows: cả dòng có id lẫn dòng cổ trùng tên đều về tên mới + có id
        rows = self.conn.execute(
            "SELECT worker_name, worker_id FROM production_report_rows").fetchall()
        self.assertTrue(all(r[0] == "Thảo" and r[1] == self.tho["id"] for r in rows))
        # blob bang cũng đổi tên
        bang = json.loads(self.conn.execute(
            "SELECT bang FROM production_slips WHERE thread_id=301").fetchone()[0])
        self.assertEqual(bang["rows"][0]["name"], "Thảo")
        # dashboard gom về 1 thợ duy nhất tên mới, tổng không tách
        d = dashboard(self.conn)
        self.assertEqual(len(d["by_worker"]), 1)
        self.assertEqual(d["by_worker"][0]["name"], "Thảo")
        self.assertEqual(d["by_worker"][0]["tong"], 200.0)
        self.assertEqual(worker_detail(self.conn, "Thảo")["total"], 200.0)


class CustomerKey(Base):
    def setUp(self):
        super().setUp()
        self.conn.execute(
            "CREATE TABLE customers (firebase_key TEXT PRIMARY KEY, json TEXT, "
            "updated_at INTEGER, deleted_at TEXT)")
        self.conn.commit()

    def test_same_name_twice_two_customers_no_overwrite(self):
        from order_store.customers import add_customer
        ok1, m1 = add_customer(self.conn, {"name": "Chị Hoa", "sdt": "0901"})
        ok2, m2 = add_customer(self.conn, {"name": "Chị Hoa", "sdt": "0902"})
        self.assertTrue(ok1 and ok2)
        self.assertIn("Trùng tên", m2)
        rows = self.conn.execute("SELECT firebase_key, json FROM customers").fetchall()
        self.assertEqual(len(rows), 2)                       # KHÔNG đè
        keys = {r[0] for r in rows}
        self.assertEqual(len(keys), 2)
        self.assertTrue(all(k.isdigit() for k in keys))      # key epoch-ms, không phải slug tên
        phones = {json.loads(r[1])["sdt"] for r in rows}
        self.assertEqual(phones, {"0901", "0902"})           # cả 2 khách còn nguyên

    def test_explicit_key_upserts(self):
        from order_store.customers import add_customer
        add_customer(self.conn, {"firebase_key": "46999", "name": "A"})
        add_customer(self.conn, {"firebase_key": "46999", "name": "A sửa"})
        rows = self.conn.execute("SELECT json FROM customers").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])["name"], "A sửa")


class UsernameRename(Base):
    def test_rename_cascades_tasks_comments(self):
        from user_store import add_user, get_user, rename_user
        add_user("thao", "1234", "Thảo", db_path=self.path)
        conn = self.conn
        conn.execute("CREATE TABLE web_tasks (id INTEGER PRIMARY KEY, assignee TEXT, done_by TEXT, created_by TEXT)")
        conn.execute("CREATE TABLE web_comments (id INTEGER PRIMARY KEY, username TEXT)")
        conn.execute("CREATE TABLE entity_comments (id INTEGER PRIMARY KEY, username TEXT)")
        conn.execute("CREATE TABLE order_image_comments (id INTEGER PRIMARY KEY, username TEXT)")
        conn.execute("INSERT INTO web_tasks (assignee, done_by, created_by) VALUES ('thao','thao','duy')")
        conn.execute("INSERT INTO web_comments (username) VALUES ('thao')")
        conn.commit()
        counts = rename_user("thao", "thao2", db_path=self.path)
        self.assertEqual(counts["web_users"], 1)
        self.assertEqual(counts["web_tasks.assignee"], 1)
        self.assertEqual(counts["web_comments"], 1)
        self.assertIsNone(get_user("thao", db_path=self.path))
        self.assertIsNotNone(get_user("thao2", db_path=self.path))
        row = self.conn.execute("SELECT assignee, done_by, created_by FROM web_tasks").fetchone()
        self.assertEqual((row[0], row[1], row[2]), ("thao2", "thao2", "duy"))  # duy không bị đụng

    def test_rename_validations(self):
        from user_store import add_user, rename_user
        add_user("tri", "1234", db_path=self.path)
        add_user("trang", "1234", db_path=self.path)
        for old, new in [("tri", "trang"), ("tri", "tri"), ("khongco", "x1"), ("tri", "123")]:
            with self.assertRaises(ValueError):
                rename_user(old, new, db_path=self.path)


if __name__ == "__main__":
    unittest.main()
