"""Test usage_store: cộng dồn UPSERT, lọc dữ liệu rác, tổng hợp stats theo ngày/user."""
import os
import tempfile
import unittest

import usage_store


class UsageStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.db)

    def test_record_batch_upserts_and_accumulates(self):
        events = [{"kind": "tap", "page": "#/orders", "label": "Nhận tiền", "n": 2}]
        self.assertEqual(usage_store.record_batch("duy", events, day="2026-07-13", db_path=self.db), 1)
        self.assertEqual(usage_store.record_batch("duy", events, day="2026-07-13", db_path=self.db), 1)
        stats = usage_store.stats(365, db_path=self.db)
        self.assertEqual(stats["labels"], [{"page": "#/orders", "label": "Nhận tiền", "count": 4}])

    def test_rejects_junk_events(self):
        events = [
            {"kind": "hack", "page": "#/x", "label": "a"},        # kind lạ
            {"kind": "tap", "page": "", "label": "a"},            # thiếu page
            {"kind": "tap", "page": "#/x", "label": "a", "n": 0}, # n <= 0
            {"kind": "tap", "page": "#/x", "label": "a", "n": "xyz"},
            "not-a-dict",
            {"kind": "tap", "page": "#/ok", "label": "b" * 200, "n": 99999},  # bị cắt/cap
        ]
        self.assertEqual(usage_store.record_batch("duy", events, day="2026-07-13", db_path=self.db), 1)
        row = usage_store.stats(365, db_path=self.db)["labels"][0]
        self.assertEqual(len(row["label"]), 64)
        self.assertEqual(row["count"], 1000)

    def test_stats_filters_by_days_and_user(self):
        usage_store.record_batch("duy", [{"kind": "view", "page": "#/orders"}], day="2020-01-01", db_path=self.db)
        usage_store.record_batch("duy", [{"kind": "view", "page": "#/camera"}], db_path=self.db)   # hôm nay
        usage_store.record_batch("trang", [{"kind": "tap", "page": "#/camera", "label": "Làm mới"}], db_path=self.db)
        recent = usage_store.stats(7, db_path=self.db)
        self.assertEqual([p["page"] for p in recent["pages"]], ["#/camera"])  # 2020 bị loại
        self.assertEqual(recent["pages"][0], {"page": "#/camera", "views": 1, "taps": 1})
        self.assertEqual({u["username"] for u in recent["users"]}, {"duy", "trang"})
        only_trang = usage_store.stats(7, username="trang", db_path=self.db)
        self.assertEqual(only_trang["pages"], [{"page": "#/camera", "views": 0, "taps": 1}])

    def test_views_have_empty_label_and_dont_pollute_labels(self):
        usage_store.record_batch("duy", [{"kind": "view", "page": "#/orders"}], db_path=self.db)
        self.assertEqual(usage_store.stats(7, db_path=self.db)["labels"], [])


if __name__ == "__main__":
    unittest.main()
