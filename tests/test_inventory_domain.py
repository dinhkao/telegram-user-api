"""Pure unit tests for inventory_store.domain — no DB, deterministic.

Số gọi thùng toàn kho (xoay vòng) + gộp theo size, không đụng IO.
"""
from __future__ import annotations

import unittest

from inventory_store.domain import (
    group_by_size,
    summarize,
)


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


class CallNumberTests(unittest.TestCase):
    """Số gọi toàn kho — 27 block xoay vòng (001–999 → A001…Z999 → 001)."""

    def test_call_code_pads(self):
        from inventory_store.domain import call_code
        self.assertEqual(call_code(7), "007")
        self.assertEqual(call_code(347), "347")

    def test_call_code_letter_blocks(self):
        from inventory_store.domain import call_code
        self.assertEqual(call_code(1000), "A001")     # sau 999 sang block A
        self.assertEqual(call_code(1046), "A047")
        self.assertEqual(call_code(1998), "A999")
        self.assertEqual(call_code(1999), "B001")
        self.assertEqual(call_code(26973), "Z999")    # số cuối không gian

    def test_code_call_number_new_and_legacy(self):
        from inventory_store.domain import code_call_number
        self.assertEqual(code_call_number("047"), 47)
        self.assertEqual(code_call_number("K2L-001"), 1)      # mã cũ theo SP
        self.assertEqual(code_call_number("K2L-00A"), 10)     # mã cũ base36
        self.assertEqual(code_call_number(""), 0)
        self.assertEqual(code_call_number("XYZ"), 0)

    def test_code_call_number_letter_blocks(self):
        from inventory_store.domain import code_call_number
        self.assertEqual(code_call_number("A047"), 1046)
        self.assertEqual(code_call_number("a047"), 1046)      # chữ thường → chuẩn hoá hoa
        self.assertEqual(code_call_number("Z999"), 26973)
        self.assertEqual(code_call_number("A47"), 0)          # phải đúng 3 chữ số
        self.assertEqual(code_call_number("AA47"), 0)         # đúng 1 chữ đầu
        self.assertEqual(code_call_number("A000"), 0)         # vị trí 0 không tồn tại

    def test_roundtrip_call_code_all_blocks(self):
        from inventory_store.domain import call_code, code_call_number
        for n in [1, 47, 999, 1000, 1046, 1998, 1999, 26973]:
            self.assertEqual(code_call_number(call_code(n)), n, call_code(n))

    def test_next_call_numbers_sequential_skip_taken(self):
        from inventory_store.domain import next_call_numbers
        self.assertEqual(next_call_numbers(5, {6, 8}, 3), [7, 9, 10])

    def test_next_call_numbers_crosses_into_block_a(self):
        # Hết 999 KHÔNG quay về 001 nữa — sang block A (1000 = 'A001')
        from inventory_store.domain import next_call_numbers
        self.assertEqual(next_call_numbers(999, set(), 2), [1000, 1001])
        self.assertEqual(next_call_numbers(998, {999}, 2), [1000, 1001])

    def test_next_call_numbers_wraps_at_z999(self):
        from inventory_store.domain import next_call_numbers
        self.assertEqual(next_call_numbers(26973, set(), 2), [1, 2])
        self.assertEqual(next_call_numbers(26972, {26973}, 1), [1])

    def test_next_call_numbers_exhausted_raises(self):
        from inventory_store.domain import CALL_MAX, next_call_numbers
        with self.assertRaises(ValueError):
            next_call_numbers(0, set(range(1, CALL_MAX + 1)), 1)

    def test_legacy_active_codes_reserve_numbers(self):
        # Thùng cũ K2L-003 còn hàng → số 3 bị chiếm trong vòng xoay mới
        from inventory_store.domain import code_call_number, next_call_numbers
        taken = {code_call_number(c) for c in ["K2L-003", "046"]}
        self.assertEqual(next_call_numbers(2, taken, 2), [4, 5])


if __name__ == "__main__":
    unittest.main()
