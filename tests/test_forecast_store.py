"""forecast_store: upsert theo ymd giữ id, list mới-nhất-trước + cờ viewed theo user,
mark_viewed idempotent, phân trang before_id."""
from __future__ import annotations

import os
import tempfile
import unittest

import forecast_store
from utils.db import get_connection


class ForecastStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        forecast_store.ensure_tables(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _pub(self, ymd, **kw):
        data = {"dow_label": "Thứ Ba", "lunar": {"label": "28/7 ÂL"},
                "day": {"total": 3280, "hi": 3940}, "week": {"total": 17850, "hi": 20500, "from": "2026-09-07", "to": "2026-09-13"}}
        return forecast_store.upsert_forecast(self.conn, ymd=ymd, title=kw.get("title", "T " + ymd),
                                              summary="s", body_md="b" * 10, data=data, model=kw.get("model", "auto"))

    def test_upsert_giu_id(self):
        r1, c1 = self._pub("2026-09-08")
        r2, c2 = self._pub("2026-09-08", title="Đè", model="claude-opus-5")
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(r1["id"], r2["id"])
        self.assertEqual(r2["title"], "Đè")
        self.assertEqual(r2["model"], "claude-opus-5")
        self.assertEqual(r2["day_total"], 3280)
        self.assertEqual(r2["week_from"], "2026-09-07")
        self.assertEqual(r2["lunar_label"], "28/7 ÂL")
        self.assertIn("body_md", r2)

    def test_list_viewed_phan_trang(self):
        ids = [self._pub(f"2026-09-0{i}")[0]["id"] for i in range(1, 6)]
        forecast_store.mark_viewed(self.conn, ids[-1], "duy")
        forecast_store.mark_viewed(self.conn, ids[-1], "duy")   # idempotent
        items, more = forecast_store.list_forecasts(self.conn, limit=2, username="duy")
        self.assertTrue(more)
        self.assertEqual([i["ymd"] for i in items], ["2026-09-05", "2026-09-04"])
        self.assertEqual([i["viewed"] for i in items], [True, False])
        self.assertNotIn("body_md", items[0])
        items2, more2 = forecast_store.list_forecasts(self.conn, limit=10, before_id=items[-1]["id"], username="duy")
        self.assertFalse(more2)
        self.assertEqual(len(items2), 3)
        self.assertTrue(forecast_store.viewed_by(self.conn, ids[-1], "duy"))
        self.assertFalse(forecast_store.viewed_by(self.conn, ids[-1], "khac"))
        self.assertIsNone(forecast_store.get_by_ymd(self.conn, "2030-01-01"))

    def test_ymd_xau(self):
        with self.assertRaises(ValueError):
            self._pub("2026-9-8")


if __name__ == "__main__":
    unittest.main()
