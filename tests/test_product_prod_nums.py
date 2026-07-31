"""Sửa THÔNG SỐ SẢN XUẤT của SP (số cây/1 mâm + lượng 1 mẻ) qua POST /api/products/{code}.

Chốt: chỉ VĂN PHÒNG sửa được 2 số này (chúng vào công thức tổng cây của báo cáo SX →
ra tiền công), rỗng/0 = xoá về NULL (chưa đặt → lùi về SP_INFO), số xấu bị chặn, và
các field khác của endpoint vẫn mở như cũ cho mọi người đăng nhập.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import server_app.product_routes as pr
from product_store.queries import get_product, upsert_product
from product_store.schema import create_products_table
from utils.db import get_connection


class ProductProdNumsTest(AioHTTPTestCase):
    async def get_application(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = get_connection(self.path)
        create_products_table(conn)
        upsert_product(conn, "K10LV87", name="Kẹo 10", prod_mam=3, prod_luong=1100)
        conn.commit()
        conn.close()
        # route dùng DB tạm + không ghi audit thật; office bật/tắt được trong từng test
        self._orig = (pr._get_connection, pr._audit_product, pr.office_user)
        pr._get_connection = lambda: get_connection(self.path)
        pr._audit_product = lambda *a, **k: None
        self._office = {"who": True}
        pr.office_user = lambda req: {"username": "vp"} if self._office["who"] else None

        app = web.Application()
        app.router.add_post("/api/products/{code}", pr.product_update_handler)
        return app

    async def tearDownAsync(self):
        pr._get_connection, pr._audit_product, pr.office_user = self._orig
        os.unlink(self.path)

    def _prod(self):
        conn = get_connection(self.path)
        try:
            return get_product(conn, "K10LV87")
        finally:
            conn.close()

    async def _post(self, body):
        return await self.client.post("/api/products/K10LV87", json=body)

    async def test_van_phong_sua_duoc_ca_so_le(self):
        self._office["who"] = True
        r = await self._post({"prod_mam": "3,5", "prod_luong": 720})   # gõ dấu phẩy vẫn nhận
        self.assertEqual(r.status, 200)
        p = self._prod()
        self.assertEqual(p["prod_mam"], 3.5)
        self.assertEqual(p["prod_luong"], 720)

    async def test_bo_trong_hoac_0_la_xoa_ve_chua_dat(self):
        self._office["who"] = True
        self.assertEqual((await self._post({"prod_mam": ""})).status, 200)
        self.assertIsNone(self._prod()["prod_mam"])          # NULL = chưa đặt
        self.assertEqual((await self._post({"prod_mam": 4})).status, 200)
        self.assertEqual((await self._post({"prod_mam": 0})).status, 200)
        self.assertIsNone(self._prod()["prod_mam"])          # 0 cũng = chưa đặt

    async def test_so_xau_bi_chan(self):
        self._office["who"] = True
        for bad in ("abc", -1, float("nan"), float("inf")):
            r = await self._post({"prod_mam": bad})
            self.assertEqual(r.status, 400, f"phải chặn {bad!r}")
        self.assertEqual(self._prod()["prod_mam"], 3)        # giữ nguyên số cũ

    async def test_staff_khong_sua_duoc_nhung_van_sua_duoc_field_khac(self):
        self._office["who"] = False
        r = await self._post({"prod_mam": 9})
        self.assertEqual(r.status, 403)
        self.assertEqual(self._prod()["prod_mam"], 3)        # không đổi
        # field thường vẫn mở như trước (endpoint này vốn không chặn)
        self.assertEqual((await self._post({"note": "ghi chú"})).status, 200)
        self.assertEqual(self._prod()["note"], "ghi chú")

    async def test_khong_gui_thi_khong_dung_toi(self):
        self._office["who"] = True
        self.assertEqual((await self._post({"name": "Tên mới"})).status, 200)
        p = self._prod()
        self.assertEqual(p["name"], "Tên mới")
        self.assertEqual(p["prod_mam"], 3)                   # vắng key = giữ nguyên
        self.assertEqual(p["prod_luong"], 1100)


if __name__ == "__main__":
    unittest.main()
