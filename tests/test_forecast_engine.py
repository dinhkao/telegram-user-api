"""Engine dự báo (forecast_store.engine.compute) trên dữ liệu tổng hợp: nhịp đều →
dự báo = nhịp; hệ số âm lịch kẹp; sofar/remain tuần; nhóm không có nền thì 1,0;
narrative tự động có đủ mục + số."""
from __future__ import annotations

import datetime as dt
import unittest

from forecast_store.engine import compute
from forecast_store.narrative import auto_narrative, summary_for


def _lines(per_day: dict[str, float], start: dt.date, end: dt.date, boost=None):
    """1 đơn/ngày/nhóm với sl = per_day[fam] (× boost(date) nếu có)."""
    out = []
    d = start
    tid = 1
    while d <= end:
        for fam, q in per_day.items():
            k = boost(d, fam) if boost else 1.0
            out.append({"date": d, "tid": tid, "fam": fam, "code": fam, "name": f"SP {fam}",
                        "unit": "cây", "sl": q * k})
            tid += 1
        d += dt.timedelta(days=1)
    return out


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.today = dt.date(2026, 9, 8)   # Thứ Ba
        self.start = self.today - dt.timedelta(days=420)

    def test_nhip_deu(self):
        lines = _lines({"A": 100.0, "B": 10.0}, self.start, self.today - dt.timedelta(days=1))
        d = compute(lines, self.today)
        self.assertEqual(d["dow_label"], "Thứ Ba")
        self.assertEqual(d["lunar"]["label"], "28/7 ÂL Bính Ngọ")
        a = next(r for r in d["day"]["rows"] if r["fam"] == "A")
        self.assertAlmostEqual(a["fc"], 100, delta=2)       # 700/tuần × 1/7 × factor 1
        self.assertEqual(a["factor"], 1.0)
        wa = next(r for r in d["week"]["rows"] if r["fam"] == "A")
        self.assertAlmostEqual(wa["fc"], 700, delta=5)
        self.assertEqual(wa["sofar"], 100.0)                # đã bán T2 (hôm nay chưa có)
        self.assertAlmostEqual(wa["remain"], 600, delta=5)
        self.assertEqual(d["week"]["from"], "2026-09-07")
        self.assertEqual(d["week"]["to"], "2026-09-13")
        self.assertEqual(d["yesterday"]["total"], 110)
        self.assertEqual(len(d["last7"]), 7)
        self.assertEqual(d["events"][0]["name"], "Trung thu")

    def test_he_so_am_lich_kep(self):
        # năm ngoái đúng tuần âm lịch này (18–24/9/2025) bán gấp 3 → factor kẹp 1,5 → fc = base × 1,25
        ly_from, ly_to = dt.date(2025, 9, 18), dt.date(2025, 9, 24)
        lines = _lines({"A": 100.0}, self.start, self.today - dt.timedelta(days=1),
                       boost=lambda d, f: 3.0 if ly_from <= d <= ly_to else 1.0)
        d = compute(lines, self.today)
        wa = d["week"]["rows"][0]
        self.assertEqual(wa["factor"], 1.5)
        self.assertAlmostEqual(wa["fc"], 700 * 1.25, delta=10)
        da = d["day"]["rows"][0]
        self.assertGreater(da["factor"], 1.0)

    def test_nhom_moi_khong_co_nen(self):
        # nhóm chỉ bán 30 ngày gần đây → factor 1,0, vẫn có dự báo
        lines = _lines({"N": 50.0}, self.today - dt.timedelta(days=30), self.today - dt.timedelta(days=1))
        d = compute(lines, self.today)
        self.assertEqual(d["week"]["rows"][0]["factor"], 1.0)
        self.assertAlmostEqual(d["week"]["rows"][0]["fc"], 350, delta=5)

    def test_narrative(self):
        lines = _lines({"A": 100.0}, self.start, self.today - dt.timedelta(days=1))
        d = compute(lines, self.today, prev_day_forecast=95)
        title, summary, body = auto_narrative(d)
        self.assertEqual(title, "Dự báo hàng hoá Thứ Ba 8/9")
        self.assertIn("Nhu cầu hôm nay khoảng", summary)
        self.assertIn("Trung thu còn 17 ngày", summary_for(d))
        for h in ("## Ưu tiên sản xuất hôm nay", "## Kế hoạch tuần", "## Yếu tố mùa vụ", "## Lưu ý"):
            self.assertIn(h, body)
        self.assertIn("dự báo hôm qua là 95", body)
        self.assertIn("ưu tiên 1", body)
        # giọng nghiêm túc: không xưng hô / khẩu ngữ
        for bad in ("anh em", "khỏi", "dư tay", "kha khá", "là ăn", "coi chừng"):
            self.assertNotIn(bad, body.lower())
            self.assertNotIn(bad, summary.lower())
        self.assertNotIn("|", body)   # không bảng — app tự hiện bảng số


if __name__ == "__main__":
    unittest.main()
