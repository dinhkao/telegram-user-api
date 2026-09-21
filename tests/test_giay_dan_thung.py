"""Giấy dán thùng: luật thuần (server_app/gdt_domain) + HTML nhãn (renderers/giay_dan_thung)
+ nhãn lịch sử (event_format). Không IO."""
from __future__ import annotations

import re
import unittest

from renderers.giay_dan_thung import FONT_MAX, FONT_MIN, LABEL_W, fit_font_px, generate_gdt_html, label_lines
from server_app.event_format import event_entry
from server_app.gdt_domain import build_prefill, contact_from, fmt_thu_ho, gdt_of, normalize_body, summary

GDT = {"ten_gdt": "Vườn xoài Út Khuyến", "sdt_gdt": "0978 237 353", "so_thung": "1", "note_gdt": "Thu hộ 700,000"}


class DomainTest(unittest.TestCase):
    def test_normalize_web_keys_and_blob_keys(self):
        g, err = normalize_body({"ten": "  A   B ", "sdt": "0909", "so_thung": "3", "note": ""})
        self.assertIsNone(err)
        self.assertEqual(g, {"ten_gdt": "A B", "sdt_gdt": "0909", "so_thung": "3", "note_gdt": ""})
        g2, _ = normalize_body(GDT)
        self.assertEqual(g2, GDT)

    def test_normalize_requires_name_and_boxes(self):
        self.assertEqual(normalize_body({"sdt": "1", "so_thung": "2"}), (None, "Thiếu tên người nhận"))
        self.assertEqual(normalize_body({"ten": "A"}), (None, "Thiếu số thùng"))
        self.assertEqual(normalize_body(None)[1], "Thiếu tên người nhận")

    def test_gdt_of(self):
        self.assertIsNone(gdt_of(None))
        self.assertIsNone(gdt_of({"giay_dan_thung": "xxx"}))
        self.assertIsNone(gdt_of({"giay_dan_thung": {"ten_gdt": "", "so_thung": ""}}))
        self.assertEqual(gdt_of({"giay_dan_thung": {"ten_gdt": "A", "so_thung": 2}}),
                         {"ten_gdt": "A", "sdt_gdt": "", "so_thung": "2", "note_gdt": ""})

    def test_fmt_thu_ho(self):
        self.assertEqual(fmt_thu_ho(700000), "Thu hộ 700,000")
        self.assertEqual(fmt_thu_ho(0), "")
        self.assertEqual(fmt_thu_ho(None), "")
        self.assertEqual(fmt_thu_ho("abc"), "")

    def test_prefill_saved_wins(self):
        self.assertEqual(build_prefill({"giay_dan_thung": GDT}, {"name": "X", "gdt_contact": {"ten": "Y"}}, 5), GDT)

    def test_prefill_from_customer_contact_then_name(self):
        p = build_prefill({}, {"name": "Chị Dung", "gdt_contact": {"ten": "Anh Hiệp", "sdt": "0939"}}, 250000)
        self.assertEqual((p["ten_gdt"], p["sdt_gdt"], p["so_thung"], p["note_gdt"]), ("Anh Hiệp", "0939", "", "Thu hộ 250,000"))
        p2 = build_prefill({"customer_name": "Đơn KH"}, {"name": "Chị Dung"}, 0)
        self.assertEqual((p2["ten_gdt"], p2["sdt_gdt"], p2["note_gdt"]), ("Chị Dung", "", ""))
        p3 = build_prefill({"kh": "Từ đơn"}, None, None)
        self.assertEqual(p3["ten_gdt"], "Từ đơn")

    def test_contact_and_summary(self):
        self.assertEqual(contact_from(GDT), {"ten": GDT["ten_gdt"], "sdt": GDT["sdt_gdt"]})
        self.assertEqual(summary(GDT), "Vườn xoài Út Khuyến · 0978 237 353 · 1 thùng · Thu hộ 700,000")
        self.assertEqual(summary({"ten_gdt": "A", "so_thung": "2"}), "A · 2 thùng")


class RendererTest(unittest.TestCase):
    def test_lines_follow_legacy_template(self):
        self.assertEqual(label_lines(GDT, sender="Kẹo Lê Trang 0941 586 542"), [
            "Người gửi: Kẹo Lê Trang 0941 586 542",
            "Người nhận: Vườn xoài Út Khuyến 0978 237 353",
            "1 (thùng)",
            "Thu hộ 700,000",
        ])
        # ghi chú rỗng → không có dòng trống; không SĐT → không thừa khoảng trắng
        self.assertEqual(label_lines({"ten_gdt": "A", "so_thung": "2"}, sender="S"), ["Người gửi: S", "Người nhận: A", "2 (thùng)"])

    def test_fit_font_shrinks_long_lines_within_bounds(self):
        self.assertEqual(fit_font_px("1 (thùng)"), FONT_MAX)
        self.assertEqual(fit_font_px(""), FONT_MAX)
        long = "Người nhận: " + "Nguyễn Văn Rất Rất Dài " * 4
        f = fit_font_px(long)
        self.assertLess(f, FONT_MAX)
        self.assertGreaterEqual(f, FONT_MIN)
        self.assertEqual(fit_font_px("x" * 5000), FONT_MIN)
        # dài hơn → không lớn hơn
        self.assertLessEqual(fit_font_px(long + "abc"), f)

    def test_html_shape_for_thermal_printer(self):
        html = generate_gdt_html(GDT, sender="S<&>")
        self.assertIn("writing-mode: vertical-rl", html)
        self.assertIn(f"width: {LABEL_W}px", html)          # cùng bề rộng hoá đơn nhiệt
        self.assertIn("@page { margin: 0; }", html)
        self.assertIn("Người gửi: S&lt;&amp;&gt;", html)      # escape
        self.assertIn("Thu hộ 700,000", html)
        self.assertNotIn("http://", html)                     # không tài nguyên ngoài
        self.assertNotIn("https://", html)
        self.assertNotIn("outline:", html)
        self.assertIn("outline:1px solid", generate_gdt_html(GDT, preview=True))
        # mỗi dòng có cỡ chữ riêng, không vượt trần
        for px in re.findall(r"font-size:(\d+)px", html):
            self.assertLessEqual(int(px), FONT_MAX)


class EventFormatTest(unittest.TestCase):
    def test_labels(self):
        label, parts = event_entry("order.gdt_saved", {**GDT, "created": True}, None)
        self.assertEqual(label, "Tạo giấy dán thùng")
        self.assertIn("1 thùng", parts[0]["t"])
        label, parts = event_entry("order.gdt_printed", {**GDT, "copies": 2}, None)
        self.assertEqual(label, "In giấy dán thùng")
        self.assertTrue(parts[0]["t"].startswith("2 tờ · "))


if __name__ == "__main__":
    unittest.main()
