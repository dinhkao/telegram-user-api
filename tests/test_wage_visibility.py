"""Quyền XEM LƯƠNG: staff KHÔNG được thấy cột tiền, văn phòng thì có.

Chốt 2 chỗ dễ rò (cột tiền nằm chung payload dùng cho việc khác):
- GET /api/workers → hourly_rate + monthly_salary (mốc lương tháng)
- GET /api/production/{id} → luong_1sp (đơn giá lương /1SP của phiếu)
Mọi endpoint lương-thuần (/api/payroll/*, /api/wages, /api/production/wages,
report-slips…) đã chặn thẳng bằng office_user → 403, không cần lọc field.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import server_app.worker_routes as wr
import server_app.production_routes as pr
import server_app.production_wages as pw
from utils.db import get_connection
from worker_store import add_worker, ensure_table, update_worker


class WageVisibilityTest(AioHTTPTestCase):
    async def get_application(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = get_connection(self.path)
        ensure_table(conn)
        self.wid = add_worker(conn, "An")["id"]
        update_worker(conn, self.wid, hourly_rate=30000, monthly_salary=6_500_000)
        conn.execute("CREATE TABLE IF NOT EXISTS production_slips (thread_id INTEGER PRIMARY KEY,"
                     " sp_name TEXT, luong_1sp REAL, kind TEXT, bang TEXT, numbers TEXT,"
                     " product_id INTEGER, lock_override TEXT, date_code TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, code TEXT)")
        from inventory_store.schema import create_inventory_table
        create_inventory_table(conn)   # detail handler đếm thùng theo phiếu
        conn.execute("INSERT INTO production_slips (thread_id, sp_name, luong_1sp, kind) "
                     "VALUES (77, 'K10LV87', 2000, 'san_xuat')")
        conn.commit()
        conn.close()
        # mọi kết nối của route đi vào DB tạm (nhớ bản gốc để TRẢ LẠI ở tearDown —
        # vá module toàn cục mà không hoàn là các test khác ăn theo DB tạm này)
        self._orig = (wr._conn, pr._conn, pw.is_office_username)
        wr._conn = lambda: get_connection(self.path)
        pr._conn = lambda: get_connection(self.path)
        self._office = {"who": False}
        pw.is_office_username = lambda u: self._office["who"]

        app = web.Application()
        app.router.add_get("/api/workers", wr.workers_list_handler)
        app.router.add_get("/api/production/{thread_id}", pr.production_detail_handler)
        return app

    async def tearDownAsync(self):
        wr._conn, pr._conn, pw.is_office_username = self._orig
        os.unlink(self.path)

    async def test_staff_khong_thay_cot_tien(self):
        self._office["who"] = False
        w = (await (await self.client.get("/api/workers")).json())["workers"][0]
        self.assertNotIn("hourly_rate", w)
        self.assertNotIn("monthly_salary", w)      # mốc lương tháng = tiền
        self.assertIn("name", w)                    # phần dùng cho báo cáo vẫn còn
        slip = (await (await self.client.get("/api/production/77")).json())["slip"]
        self.assertNotIn("luong_1sp", slip)         # đơn giá lương phiếu
        self.assertEqual(slip["sp_name"], "K10LV87")

    async def test_van_phong_van_thay_du(self):
        self._office["who"] = True
        w = (await (await self.client.get("/api/workers")).json())["workers"][0]
        self.assertEqual(w["hourly_rate"], 30000)
        self.assertEqual(w["monthly_salary"], 6_500_000)
        slip = (await (await self.client.get("/api/production/77")).json())["slip"]
        self.assertEqual(slip["luong_1sp"], 2000)


if __name__ == "__main__":
    unittest.main()
