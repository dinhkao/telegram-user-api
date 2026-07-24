"""Test area_store: CRUD khu vực (thêm/list/xoá mềm/sửa), get_or_create_report
idempotent theo ngày, xoá mềm rồi tạo lại được cùng ngày (partial unique index),
domain.last_n_days + build_dashboard_rows ('reported' chỉ khi có ảnh)."""
from __future__ import annotations

import os
import tempfile
import unittest

import area_store
from area_store import domain
from utils.db import get_connection


class AreaStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        area_store.ensure_tables(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    # ── Khu vực CRUD ─────────────────────────────────────────────────────────
    def test_add_requires_name(self):
        area, err = area_store.add_area(self.conn, "  ", by="duy")
        self.assertIsNone(area)
        self.assertIn("tên", err.lower())

    def test_add_list_and_soft_delete(self):
        a1, _ = area_store.add_area(self.conn, "Khu đóng gói", note="tầng 1", by="duy")
        a2, _ = area_store.add_area(self.conn, "Khu nấu", by="duy")
        self.assertEqual(a1["name"], "Khu đóng gói")
        self.assertEqual(a1["note"], "tầng 1")
        names = {a["name"] for a in area_store.list_areas(self.conn)}
        self.assertEqual(names, {"Khu đóng gói", "Khu nấu"})

        ok, err = area_store.soft_delete_area(self.conn, a2["id"], by="duy")
        self.assertTrue(ok)
        self.assertIsNone(err)
        names = {a["name"] for a in area_store.list_areas(self.conn)}
        self.assertEqual(names, {"Khu đóng gói"})
        self.assertIsNone(area_store.get_area(self.conn, a2["id"]))   # get bỏ xoá mềm
        # xoá lần 2 → lỗi
        ok, err = area_store.soft_delete_area(self.conn, a2["id"], by="duy")
        self.assertFalse(ok)
        self.assertIn("xoá", err.lower())

    def test_update_area(self):
        a, _ = area_store.add_area(self.conn, "Khu A", by="duy")
        upd, err = area_store.update_area(self.conn, a["id"], name="Khu A1", note="mới")
        self.assertIsNone(err)
        self.assertEqual(upd["name"], "Khu A1")
        self.assertEqual(upd["note"], "mới")
        # tên rỗng bị chặn
        _, err = area_store.update_area(self.conn, a["id"], name="   ")
        self.assertIsNotNone(err)
        # chỉ đổi note, giữ tên
        upd2, err = area_store.update_area(self.conn, a["id"], note="ghi chú 2")
        self.assertIsNone(err)
        self.assertEqual(upd2["name"], "Khu A1")
        self.assertEqual(upd2["note"], "ghi chú 2")
        # id không tồn tại
        _, err = area_store.update_area(self.conn, 9999, name="x")
        self.assertIsNotNone(err)

    # ── Báo cáo vệ sinh ──────────────────────────────────────────────────────
    def test_get_or_create_idempotent_per_day(self):
        a, _ = area_store.add_area(self.conn, "Khu A", by="duy")
        r1, created1 = area_store.get_or_create_report(self.conn, a["id"], "2026-07-24", by="duy")
        self.assertTrue(created1)
        r2, created2 = area_store.get_or_create_report(self.conn, a["id"], "2026-07-24", by="tho")
        self.assertFalse(created2)
        self.assertEqual(r1["id"], r2["id"])   # cùng ngày → cùng báo cáo
        # ngày khác → báo cáo mới
        r3, created3 = area_store.get_or_create_report(self.conn, a["id"], "2026-07-25", by="duy")
        self.assertTrue(created3)
        self.assertNotEqual(r3["id"], r1["id"])

    def test_soft_delete_report_allows_new_same_day(self):
        a, _ = area_store.add_area(self.conn, "Khu A", by="duy")
        r1, _ = area_store.get_or_create_report(self.conn, a["id"], "2026-07-24", by="duy")
        ok, err = area_store.soft_delete_report(self.conn, r1["id"], by="duy")
        self.assertTrue(ok)
        self.assertIsNone(err)
        # partial unique index chỉ áp cho dòng CÒN SỐNG → tạo lại cùng ngày OK, id mới
        r2, created = area_store.get_or_create_report(self.conn, a["id"], "2026-07-24", by="duy")
        self.assertTrue(created)
        self.assertNotEqual(r2["id"], r1["id"])
        # danh sách chỉ còn báo cáo mới
        ids = [r["id"] for r in area_store.list_reports(self.conn, a["id"])]
        self.assertEqual(ids, [r2["id"]])

    def test_list_reports_since(self):
        a, _ = area_store.add_area(self.conn, "Khu A", by="duy")
        b, _ = area_store.add_area(self.conn, "Khu B", by="duy")
        area_store.get_or_create_report(self.conn, a["id"], "2026-07-20", by="duy")
        area_store.get_or_create_report(self.conn, b["id"], "2026-07-24", by="duy")
        since = area_store.list_reports_since(self.conn, "2026-07-22")
        self.assertEqual({r["ymd"] for r in since}, {"2026-07-24"})

    # ── Domain thuần ─────────────────────────────────────────────────────────
    def test_last_n_days(self):
        self.assertEqual(domain.last_n_days("2026-07-24", 3),
                         ["2026-07-22", "2026-07-23", "2026-07-24"])
        self.assertEqual(domain.last_n_days("2026-07-24", 1), ["2026-07-24"])
        self.assertEqual(domain.last_n_days("2026-07-24", 0), [])

    def test_build_dashboard_rows_reported_needs_photo(self):
        areas = [{"id": 1, "name": "Khu A", "note": ""}, {"id": 2, "name": "Khu B", "note": ""}]
        today = "2026-07-24"
        reports = [
            # khu A hôm nay có ảnh → đã báo cáo
            {"id": 10, "area_id": 1, "ymd": today, "created_at": "2026-07-24T02:00:00+00:00",
             "created_by": "duy", "photo_count": 2},
            # khu B hôm nay CHƯA có ảnh → CHƯA tính là báo cáo
            {"id": 11, "area_id": 2, "ymd": today, "created_at": "2026-07-24T01:00:00+00:00",
             "created_by": "tho", "photo_count": 0},
            # khu A hôm qua có ảnh (cho dải tuần)
            {"id": 9, "area_id": 1, "ymd": "2026-07-23", "created_at": "2026-07-23T02:00:00+00:00",
             "created_by": "duy", "photo_count": 1},
        ]
        rows, done = domain.build_dashboard_rows(areas, reports, today, week=7)
        self.assertEqual(done, 1)   # chỉ khu A
        by_id = {r["id"]: r for r in rows}
        self.assertTrue(by_id[1]["today"]["reported"])
        self.assertEqual(by_id[1]["today"]["report_id"], 10)
        self.assertEqual(by_id[1]["today"]["photo_count"], 2)
        self.assertFalse(by_id[2]["today"]["reported"])
        self.assertEqual(by_id[2]["today"]["report_id"], 11)   # có báo cáo nhưng chưa ảnh
        # dải 7 ngày: khu A đã báo cáo hôm nay + hôm qua
        weekA = {d["ymd"]: d["reported"] for d in by_id[1]["week"]}
        self.assertEqual(len(by_id[1]["week"]), 7)
        self.assertTrue(weekA["2026-07-24"])
        self.assertTrue(weekA["2026-07-23"])
        self.assertFalse(weekA["2026-07-22"])
        # last_report của khu A = báo cáo mới nhất (hôm nay)
        self.assertEqual(by_id[1]["last_report"]["ymd"], today)
        self.assertEqual(by_id[1]["last_report"]["created_by"], "duy")


if __name__ == "__main__":
    unittest.main()
