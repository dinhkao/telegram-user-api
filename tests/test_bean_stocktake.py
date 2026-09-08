"""Test PHIẾU KIỂM KHO ĐẬU (bean_store.stocktakes): chụp sổ lúc tạo, ghi số đếm kép
(bao + kg), chốt → 1 phiếu điều chỉnh với delta = đếm − sổ LÚC CHỤP (không đè biến
động sau khi đếm), cờ stale + đồng bộ sổ, 1 nháp/kho, huỷ, guard tồn âm; logic
thuần domain.count_to_base / stocktake_summary."""
from __future__ import annotations

import os
import tempfile
import unittest

import bean_store
from bean_store import domain


class BeanStocktakeTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        from utils.db import get_connection
        self.conn = get_connection(self.path)
        bean_store.ensure_tables(self.conn)
        self.kho, _ = bean_store.add_place(self.conn, "Kho A", by="duy")
        self.kho_b, _ = bean_store.add_place(self.conn, "Kho B", by="duy")
        self.xanh, _ = bean_store.add_bean(self.conn, "Đậu xanh", by="duy")
        self.phong, _ = bean_store.add_bean(self.conn, "Đậu phộng", by="duy")
        self.bao, _ = bean_store.add_unit(self.conn, self.xanh["id"], "bao", 50, "kg")
        bean_store.create_slip(self.conn, "nhap", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 200},
                                {"bean_id": self.phong["id"], "quantity": 30}], by="duy")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _stock(self, bean):
        return bean_store.stock_of(self.conn, bean["id"], self.kho["id"])

    # ── domain thuần ─────────────────────────────────────────────────────────
    def test_count_to_base(self):
        self.assertIsNone(domain.count_to_base(None, None, 50))
        self.assertEqual(domain.count_to_base(3, 12, 50), 162)
        self.assertEqual(domain.count_to_base(None, 0, 50), 0)      # đếm ra 0 ≠ chưa đếm
        self.assertEqual(domain.count_to_base(2, None, 1), 2)

    def test_summary(self):
        s = domain.stocktake_summary([
            {"expected_qty": 10, "counted_qty": 12}, {"expected_qty": 10, "counted_qty": 7},
            {"expected_qty": 5, "counted_qty": 5}, {"expected_qty": 5, "counted_qty": None}])
        self.assertEqual((s["total"], s["counted"], s["uncounted"]), (4, 3, 1))
        self.assertEqual((s["match"], s["over"], s["short"]), (1, 1, 1))
        self.assertEqual((s["sum_over"], s["sum_short"]), (2, -3))

    # ── tạo + chụp sổ ────────────────────────────────────────────────────────
    def test_create_snapshots_all_beans(self):
        st, err = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(st["status"], "draft")
        exp = {i["bean_name"]: i["expected_qty"] for i in st["items"]}
        self.assertEqual(exp, {"Đậu phộng": 30, "Đậu xanh": 200})
        self.assertTrue(all(i["counted_qty"] is None for i in st["items"]))
        self.assertEqual(st["summary"]["uncounted"], 2)
        # 1 nháp/kho
        _, err = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        self.assertIn("chưa chốt", err)
        # kho khác vẫn mở được
        st_b, err = bean_store.create_stocktake(self.conn, self.kho_b["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual([i["expected_qty"] for i in st_b["items"]], [0, 0])

    # ── đếm kép + chốt ───────────────────────────────────────────────────────
    def test_count_and_complete_creates_adjustment(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        st, err = bean_store.set_counts(self.conn, st["id"], [
            {"bean_id": self.xanh["id"], "bulk": "3", "loose": "12,5", "unit_id": self.bao["id"]},
            {"bean_id": self.phong["id"], "loose": "30"},
        ], by="tho")
        self.assertIsNone(err)
        by = {i["bean_id"]: i for i in st["items"]}
        self.assertEqual(by[self.xanh["id"]]["counted_qty"], 162.5)   # 3×50 + 12,5
        self.assertEqual(by[self.xanh["id"]]["diff"], -37.5)
        self.assertEqual(by[self.xanh["id"]]["unit_name"], "bao")
        self.assertEqual(by[self.xanh["id"]]["counted_bulk"], 3)
        self.assertEqual(by[self.phong["id"]]["diff"], 0)
        self.assertEqual(st["summary"]["short"], 1)
        self.assertEqual(st["summary"]["match"], 1)

        done, err = bean_store.complete_stocktake(self.conn, st["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(done["status"], "done")
        self.assertIsNotNone(done["slip_id"])
        self.assertEqual(done["slip"]["lines"], 1)          # chỉ dòng lệch vào phiếu
        slip = bean_store.get_slip(self.conn, done["slip_id"])
        self.assertEqual(slip["kind"], "dieu_chinh")
        self.assertEqual(slip["stocktake_id"], st["id"])
        self.assertEqual(slip["items"][0]["delta"], -37.5)
        self.assertEqual(self._stock(self.xanh), 162.5)
        self.assertEqual(self._stock(self.phong), 30)
        # đã chốt → khoá
        _, err = bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "1"}])
        self.assertIn("đã chốt", err)
        # kho được giải phóng → mở phiếu mới
        _, err = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        self.assertIsNone(err)

    def test_complete_requires_counts_and_skips_uncounted(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        _, err = bean_store.complete_stocktake(self.conn, st["id"], by="duy")
        self.assertIn("Chưa đếm", err)
        # chỉ đếm 1 dòng, dòng kia bỏ qua (không đụng)
        bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.phong["id"], "loose": "25"}])
        done, err = bean_store.complete_stocktake(self.conn, st["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(self._stock(self.phong), 25)
        self.assertEqual(self._stock(self.xanh), 200)

    def test_complete_all_match_makes_no_slip(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "200"}])
        done, err = bean_store.complete_stocktake(self.conn, st["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(done["status"], "done")
        self.assertIsNone(done["slip_id"])

    def test_clear_count_and_reject_negative(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "0"}])
        st = bean_store.get_stocktake(self.conn, st["id"])
        self.assertEqual(next(i for i in st["items"] if i["bean_id"] == self.xanh["id"])["counted_qty"], 0)
        st, _ = bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "", "bulk": ""}])
        self.assertIsNone(next(i for i in st["items"] if i["bean_id"] == self.xanh["id"])["counted_qty"])
        _, err = bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "-1"}])
        self.assertIn("âm", err)
        _, err = bean_store.set_counts(self.conn, st["id"], [{"bean_id": 999, "loose": "1"}])
        self.assertIn("không có trong phiếu", err)

    # ── kho biến động sau khi chụp ───────────────────────────────────────────
    def test_delta_uses_snapshot_not_live(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "190"}])  # thiếu 10
        # sau khi đếm, xuất hợp lệ 50 kg
        bean_store.create_slip(self.conn, "xuat", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 50}], by="duy")
        st = bean_store.get_stocktake(self.conn, st["id"])
        it = next(i for i in st["items"] if i["bean_id"] == self.xanh["id"])
        self.assertTrue(it["stale"])
        self.assertEqual((it["expected_qty"], it["live_qty"]), (200, 150))
        self.assertEqual(st["stale_count"], 1)
        done, err = bean_store.complete_stocktake(self.conn, st["id"], by="duy")
        self.assertIsNone(err)
        # áp đúng chênh lệch −10, KHÔNG ép tồn về 190 (sẽ nuốt mất phiếu xuất 50)
        self.assertEqual(self._stock(self.xanh), 140)

    def test_resync_keeps_counts_and_adds_new_beans(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "190"}])
        bean_store.create_slip(self.conn, "nhap", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 100}], by="duy")
        den, _ = bean_store.add_bean(self.conn, "Đậu đen", by="duy")
        st, err = bean_store.resync_stocktake(self.conn, st["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(st["stale_count"], 0)
        by = {i["bean_id"]: i for i in st["items"]}
        self.assertEqual(by[self.xanh["id"]]["expected_qty"], 300)
        self.assertEqual(by[self.xanh["id"]]["counted_qty"], 190)   # số đếm giữ nguyên
        self.assertIn(den["id"], by)
        self.assertEqual(by[den["id"]]["expected_qty"], 0)

    def test_complete_blocked_if_would_go_negative(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "20"}])  # −180
        bean_store.create_slip(self.conn, "xuat", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 150}], by="duy")     # tồn 50
        _, err = bean_store.complete_stocktake(self.conn, st["id"], by="duy")
        self.assertIn("âm kho", err)
        st = bean_store.get_stocktake(self.conn, st["id"])
        self.assertEqual(st["status"], "draft")            # all-or-nothing
        self.assertEqual(self._stock(self.xanh), 50)

    def test_void_and_list(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        v, err = bean_store.void_stocktake(self.conn, st["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(v["status"], "voided")
        self.assertEqual(self._stock(self.xanh), 200)
        st2, err = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        self.assertIsNone(err)
        rows, total = bean_store.list_stocktakes(self.conn)
        self.assertEqual(total, 2)
        self.assertEqual(rows[0]["id"], st2["id"])          # nháp lên đầu
        self.assertEqual(rows[0]["place_name"], "Kho A")
        rows, total = bean_store.list_stocktakes(self.conn, status="voided")
        self.assertEqual([r["id"] for r in rows], [st["id"]])

    def test_deleting_generated_slip_restores_and_detail_survives(self):
        st, _ = bean_store.create_stocktake(self.conn, self.kho["id"], by="duy")
        bean_store.set_counts(self.conn, st["id"], [{"bean_id": self.xanh["id"], "loose": "180"}])
        done, _ = bean_store.complete_stocktake(self.conn, st["id"], by="duy")
        bean_store.soft_delete_slip(self.conn, done["slip_id"], by="admin")
        self.assertEqual(self._stock(self.xanh), 200)
        st = bean_store.get_stocktake(self.conn, st["id"])
        self.assertEqual(st["status"], "done")
        self.assertIsNone(st["slip"])                       # link báo phiếu đã xoá


if __name__ == "__main__":
    unittest.main()


# ── HTTP: route kiểm kho đậu (server_app.bean_stocktake_routes) ──────────────
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import AioHTTPTestCase  # noqa: E402

import server_app.bean_stocktake_routes as bsr  # noqa: E402


class BeanStocktakeRoutesTest(AioHTTPTestCase):
    async def get_application(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        from utils.db import get_connection
        self._orig = (bsr._conn, bsr._emit, bsr.audit, bsr._office, bsr._notify_slip)
        self.audits: list = []
        self.notified: list = []
        self.office = True

        def _conn():
            c = get_connection(self.path)
            bean_store.ensure_tables(c)
            return c

        async def _office(_req):
            return self.office
        bsr._conn = _conn
        bsr._emit = lambda: None
        bsr.audit = lambda action, eid, req, payload, scope="bean_item": self.audits.append((action, scope, payload))
        bsr._office = _office
        bsr._notify_slip = lambda slip_id, actor: self.notified.append(slip_id)

        c = _conn()
        self.kho, _ = bean_store.add_place(c, "Kho A", by="duy")
        self.xanh, _ = bean_store.add_bean(c, "Đậu xanh", by="duy")
        bean_store.create_slip(c, "nhap", self.kho["id"], [{"bean_id": self.xanh["id"], "quantity": 100}], by="duy")
        c.close()

        @web.middleware
        async def fake_auth(request, handler):
            request["web_user"] = {"username": "tho", "display_name": "Thợ A"}
            return await handler(request)
        app = web.Application(middlewares=[fake_auth])
        r = app.router
        r.add_get("/api/beans/stocktakes", bsr.bean_stocktakes_handler)
        r.add_post("/api/beans/stocktakes", bsr.bean_stocktake_create_handler)
        r.add_get("/api/beans/stocktakes/{id}", bsr.bean_stocktake_detail_handler)
        r.add_post("/api/beans/stocktakes/{id}/count", bsr.bean_stocktake_count_handler)
        r.add_post("/api/beans/stocktakes/{id}/resync", bsr.bean_stocktake_resync_handler)
        r.add_post("/api/beans/stocktakes/{id}/complete", bsr.bean_stocktake_complete_handler)
        r.add_post("/api/beans/stocktakes/{id}/void", bsr.bean_stocktake_void_handler)
        return app

    async def tearDownAsync(self):
        bsr._conn, bsr._emit, bsr.audit, bsr._office, bsr._notify_slip = self._orig
        os.unlink(self.path)

    async def test_full_flow_over_http(self):
        r = await self.client.post("/api/beans/stocktakes", json={"place_id": self.kho["id"]})
        self.assertEqual(r.status, 200)
        st = (await r.json())["stocktake"]
        self.assertEqual(st["created_by"], "Thợ A")
        # trùng nháp → 400
        r = await self.client.post("/api/beans/stocktakes", json={"place_id": self.kho["id"]})
        self.assertEqual(r.status, 400)
        # ghi số đếm
        r = await self.client.post(f"/api/beans/stocktakes/{st['id']}/count",
                                   json={"items": [{"bean_id": self.xanh["id"], "loose": "90"}]})
        self.assertEqual(r.status, 200)
        d = (await r.json())["stocktake"]
        self.assertEqual(d["items"][0]["diff"], -10)
        self.assertEqual(self.audits[-1][0], "bean.stocktake_counted")
        self.assertEqual(self.audits[-1][1], "bean_stocktake")
        self.assertEqual(self.audits[-1][2]["lines"][0]["counted"], 90)
        # danh sách
        d = await (await self.client.get("/api/beans/stocktakes?status=draft")).json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["stocktakes"][0]["summary"]["short"], 1)
        # chốt → phiếu điều chỉnh + thông báo
        r = await self.client.post(f"/api/beans/stocktakes/{st['id']}/complete", json={"note": "kiểm cuối tháng"})
        self.assertEqual(r.status, 200)
        d = (await r.json())["stocktake"]
        self.assertEqual(d["status"], "done")
        self.assertEqual(self.notified, [d["slip_id"]])
        self.assertEqual(self.audits[-1][2]["slip_id"], d["slip_id"])
        # đã chốt → count 400, void 400
        r = await self.client.post(f"/api/beans/stocktakes/{st['id']}/count",
                                   json={"items": [{"bean_id": self.xanh["id"], "loose": "1"}]})
        self.assertEqual(r.status, 400)
        r = await self.client.get("/api/beans/stocktakes/9999")
        self.assertEqual(r.status, 404)

    async def test_void_is_office_only(self):
        r = await self.client.post("/api/beans/stocktakes", json={"place_id": self.kho["id"]})
        sid = (await r.json())["stocktake"]["id"]
        self.office = False
        r = await self.client.post(f"/api/beans/stocktakes/{sid}/void", json={})
        self.assertEqual(r.status, 403)
        self.office = True
        r = await self.client.post(f"/api/beans/stocktakes/{sid}/void", json={})
        self.assertEqual(r.status, 200)
        self.assertEqual((await r.json())["stocktake"]["status"], "voided")
