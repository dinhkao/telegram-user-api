import unittest

from server_app.orders_api import _created_after_delivering_cutoff, _is_actively_delivering
from server_app.customer_routes import _summary


class DeliveringOrdersTest(unittest.TestCase):
    def test_giao_done_nop_pending_is_delivering(self):
        self.assertTrue(_is_actively_delivering({"task_status": {
            "giao_hang": {"done": True, "by": 123}, "nop_tien": {"done": False},
        }}))

    def test_nop_done_is_no_longer_delivering(self):
        self.assertFalse(_is_actively_delivering({"task_status": {
            "giao_hang": {"done": True}, "nop_tien": {"done": True},
        }}))

    def test_not_yet_delivered_is_excluded(self):
        self.assertFalse(_is_actively_delivering({"task_status": {
            "giao_hang": {"done": False}, "nop_tien": {"done": False},
        }}))

    def test_chieu_lay_tien_is_excluded(self):
        self.assertFalse(_is_actively_delivering({"task_status": {
            "giao_hang": {"done": True},
            "nop_tien": {"done": False, "note": "chieu_lay_tien"},
        }}))
        self.assertFalse(_is_actively_delivering({"task_status": {
            "giao_hang": {"done": True},
            "nop_tien": {"done": False, "note": "chiều lấy tiền"},
        }}))

    def test_only_orders_created_from_12_july_2026(self):
        self.assertFalse(_created_after_delivering_cutoff({"created": "2026-07-11T23:59:59"}))
        self.assertTrue(_created_after_delivering_cutoff({"created": "2026-07-12T00:00:00"}))
        self.assertTrue(_created_after_delivering_cutoff({"created": "2026-07-12T23:59:59"}))
        self.assertFalse(_created_after_delivering_cutoff({}))

    def test_customer_summary_exposes_nickname(self):
        self.assertEqual(_summary({"name": "Công ty Ngọc Trang", "nickname": "Ngọc Trang"}, "1")["nickname"], "Ngọc Trang")
        self.assertEqual(_summary({"name": "Liên"}, "2")["nickname"], "")


if __name__ == "__main__":
    unittest.main()
