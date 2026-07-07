"""Pure unit tests for inventory_store.domain — no DB, deterministic.

Mã thùng tự sinh + gộp theo size, không đụng IO.
"""
from __future__ import annotations

import unittest

from inventory_store.domain import (
    parse_box_seq,
    format_box_code,
    next_box_code,
    group_by_size,
    summarize,
)


class BoxCodeTests(unittest.TestCase):
    def test_parse_box_seq(self):
        # BASE36: 0-9 giống thập phân; từ 10 dùng chữ (A=10…Z=35)
        self.assertEqual(parse_box_seq("K2L-007", "K2L"), 7)
        self.assertEqual(parse_box_seq("K2L-00A", "K2L"), 10)
        self.assertEqual(parse_box_seq("K2L-0ZZ", "K2L"), 35 * 36 + 35)  # 1295
        self.assertEqual(parse_box_seq("K2L-ZZZ", "K2L"), 46655)

    def test_parse_box_seq_mismatch(self):
        self.assertEqual(parse_box_seq("ABC-001", "K2L"), 0)
        self.assertEqual(parse_box_seq("", "K2L"), 0)
        self.assertEqual(parse_box_seq("K2L-@@", "K2L"), 0)   # ký tự ngoài base36

    def test_format_base36_pads_three(self):
        self.assertEqual(format_box_code("K2L", 1), "K2L-001")
        self.assertEqual(format_box_code("K2L", 9), "K2L-009")
        self.assertEqual(format_box_code("K2L", 10), "K2L-00A")   # 10 → A
        self.assertEqual(format_box_code("K2L", 46655), "K2L-ZZZ")  # trần 3 ký tự
        self.assertEqual(format_box_code("K2L", 46656), "K2L-1000")  # tràn → 4 ký tự
        # round-trip: format ∘ parse = identity
        for s in (1, 10, 35, 36, 1000, 46655):
            self.assertEqual(parse_box_seq(format_box_code("K2L", s), "K2L"), s)

    def test_next_from_empty(self):
        self.assertEqual(next_box_code("K2L", []), "K2L-001")

    def test_next_uses_max_not_count(self):
        # có lỗ hổng (xoá thùng giữa) → vẫn lấy max+1, không tái dùng số cũ
        self.assertEqual(next_box_code("K2L", ["K2L-001", "K2L-005"]), "K2L-006")

    def test_next_ignores_other_products(self):
        self.assertEqual(next_box_code("K2L", ["ABC-009", "K2L-002"]), "K2L-003")


class GroupTests(unittest.TestCase):
    def test_group_by_size(self):
        boxes = [
            {"box_code": "K2L-001", "quantity": 50},
            {"box_code": "K2L-002", "quantity": 50},
            {"box_code": "K2L-003", "quantity": 70},
        ]
        groups = group_by_size(boxes)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0], {"quantity": 50, "count": 2, "total": 100,
                                     "box_codes": ["K2L-001", "K2L-002"]})
        self.assertEqual(groups[1]["quantity"], 70)
        self.assertEqual(groups[1]["total"], 70)

    def test_summarize(self):
        boxes = [
            {"box_code": "K2L-001", "quantity": 50},
            {"box_code": "K2L-002", "quantity": 50},
            {"box_code": "K2L-003", "quantity": 70},
        ]
        s = summarize(boxes)
        self.assertEqual(s["total"], 170)
        self.assertEqual(s["box_count"], 3)
        self.assertEqual(len(s["groups"]), 2)

    def test_empty(self):
        self.assertEqual(summarize([]), {"total": 0, "box_count": 0, "groups": []})


if __name__ == "__main__":
    unittest.main()
