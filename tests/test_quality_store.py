"""Test quality_store (BÁO CÁO CHẤT LƯỢNG MÂM KẸO): get_or_create_report idempotent
theo (thợ, ngày), xoá mềm rồi chụp lại được cùng ngày (partial unique index),
list_reports/list_reports_since, và domain.build_dashboard_rows ('reported' chỉ khi
có ảnh) trên thực thể THỢ (worker_id)."""
from __future__ import annotations

import os
import tempfile
import unittest

import quality_store
from quality_store import domain
from utils.db import get_connection


class QualityStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        quality_store.ensure_tables(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    # ── Báo cáo ──────────────────────────────────────────────────────────────
    def test_get_or_create_idempotent_per_day(self):
        r1, created1 = quality_store.get_or_create_report(self.conn, 7, "2026-07-24", by="duy")
        self.assertTrue(created1)
        r2, created2 = quality_store.get_or_create_report(self.conn, 7, "2026-07-24", by="tho")
        self.assertFalse(created2)
        self.assertEqual(r1["id"], r2["id"])          # cùng thợ, cùng ngày → cùng báo cáo
        # ngày khác → báo cáo mới
        r3, created3 = quality_store.get_or_create_report(self.conn, 7, "2026-07-25", by="duy")
        self.assertTrue(created3)
        self.assertNotEqual(r3["id"], r1["id"])
        # thợ khác cùng ngày → báo cáo riêng
        r4, created4 = quality_store.get_or_create_report(self.conn, 8, "2026-07-24", by="duy")
        self.assertTrue(created4)
        self.assertNotEqual(r4["id"], r1["id"])

    def test_soft_delete_report_allows_new_same_day(self):
        r1, _ = quality_store.get_or_create_report(self.conn, 7, "2026-07-24", by="duy")
        ok, err = quality_store.soft_delete_report(self.conn, r1["id"], by="duy")
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertIsNone(quality_store.get_report(self.conn, r1["id"]))   # get bỏ xoá mềm
        # partial unique index chỉ áp cho dòng CÒN SỐNG → chụp lại cùng ngày OK, id mới
        r2, created = quality_store.get_or_create_report(self.conn, 7, "2026-07-24", by="duy")
        self.assertTrue(created)
        self.assertNotEqual(r2["id"], r1["id"])
        ids = [r["id"] for r in quality_store.list_reports(self.conn, 7)]
        self.assertEqual(ids, [r2["id"]])
        # xoá lần 2 → lỗi
        ok, err = quality_store.soft_delete_report(self.conn, r1["id"], by="duy")
        self.assertFalse(ok)
        self.assertIn("xoá", err.lower())

    def test_list_reports_since(self):
        quality_store.get_or_create_report(self.conn, 7, "2026-07-20", by="duy")
        quality_store.get_or_create_report(self.conn, 8, "2026-07-24", by="duy")
        since = quality_store.list_reports_since(self.conn, "2026-07-22")
        self.assertEqual({r["ymd"] for r in since}, {"2026-07-24"})
        self.assertEqual({r["worker_id"] for r in since}, {8})

    def test_note_is_saved(self):
        rep, _ = quality_store.get_or_create_report(self.conn, 7, "2026-07-24", by="duy",
                                                    note="  mâm K10 hơi cháy  ")
        self.assertEqual(rep["note"], "mâm K10 hơi cháy")

    # ── Domain thuần ─────────────────────────────────────────────────────────
    def test_last_n_days(self):
        self.assertEqual(domain.last_n_days("2026-07-24", 3),
                         ["2026-07-22", "2026-07-23", "2026-07-24"])
        self.assertEqual(domain.last_n_days("2026-07-24", 0), [])

    def test_build_dashboard_rows_reported_needs_photo(self):
        workers = [{"id": 1, "name": "Thuỷ", "note": ""}, {"id": 2, "name": "Xuyên", "note": ""}]
        today = "2026-07-24"
        reports = [
            # thợ 1 hôm nay có ảnh → đã báo cáo
            {"id": 10, "worker_id": 1, "ymd": today, "created_at": "2026-07-24T02:00:00+00:00",
             "created_by": "duy", "photo_count": 2},
            # thợ 2 hôm nay CHƯA có ảnh → CHƯA tính là báo cáo
            {"id": 11, "worker_id": 2, "ymd": today, "created_at": "2026-07-24T01:00:00+00:00",
             "created_by": "tho", "photo_count": 0},
            # thợ 1 hôm qua có ảnh (cho dải tuần)
            {"id": 9, "worker_id": 1, "ymd": "2026-07-23", "created_at": "2026-07-23T02:00:00+00:00",
             "created_by": "duy", "photo_count": 1},
        ]
        rows, done = domain.build_dashboard_rows(workers, reports, today, week=7)
        self.assertEqual(done, 1)   # chỉ thợ 1
        by_id = {r["id"]: r for r in rows}
        self.assertTrue(by_id[1]["today"]["reported"])
        self.assertEqual(by_id[1]["today"]["report_id"], 10)
        self.assertEqual(by_id[1]["today"]["photo_count"], 2)
        self.assertFalse(by_id[2]["today"]["reported"])
        self.assertEqual(by_id[2]["today"]["report_id"], 11)   # có báo cáo nhưng chưa ảnh
        weekA = {d["ymd"]: d["reported"] for d in by_id[1]["week"]}
        self.assertEqual(len(by_id[1]["week"]), 7)
        self.assertTrue(weekA["2026-07-24"])
        self.assertTrue(weekA["2026-07-23"])
        self.assertFalse(weekA["2026-07-22"])
        self.assertEqual(by_id[1]["last_report"]["ymd"], today)
        self.assertEqual(by_id[1]["last_report"]["created_by"], "duy")
        self.assertEqual(by_id[1]["name"], "Thuỷ")


if __name__ == "__main__":
    unittest.main()
