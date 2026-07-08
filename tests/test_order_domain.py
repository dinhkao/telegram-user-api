"""Pure unit tests for order_store.domain — no DB, no Telegram, deterministic.

This is what the Phase 2 layering buys: business rules testable in microseconds
without any IO. now_iso is injected so results are fixed.
"""
from __future__ import annotations

import unittest

from order_store.model import Order
from order_store.domain import all_steps_done, mark_task, clear_task

NOW = "2026-01-01T00:00:00.000Z"


class OrderModelTests(unittest.TestCase):
    def test_order_is_lossless(self):
        blob = {"khach_hang": "Tú", "weird_legacy_field": [1, 2], "nested": {"a": 1}}
        order = Order.from_dict(blob)
        self.assertIs(order.to_dict(), blob)                  # same object, nothing copied/dropped
        self.assertEqual(order.to_dict(), blob)

    def test_task_status_property_never_inserts_key(self):
        order = Order.from_dict({})
        self.assertEqual(order.task_status, {})
        self.assertNotIn("task_status", order.to_dict())      # read must not create the key


class DomainTaskRules(unittest.TestCase):
    def test_mark_task_sets_payload_mirror_and_flow_version(self):
        order = mark_task(Order.from_dict({}), "soan_hang", 42, done=True, skip=False, note="", now_iso=NOW)
        d = order.to_dict()
        self.assertEqual(d["task_status"]["soan_hang"], {"done": True, "by": 42, "at": NOW, "skip": False})
        self.assertTrue(d["soan"])              # MIRROR_FIELDS soan_hang -> soan
        self.assertEqual(d["flow_version"], 2)

    def test_mark_task_skip_sets_mirror_true(self):
        order = mark_task(Order.from_dict({}), "nop_tien", 1, done=False, skip=True, note="", now_iso=NOW)
        d = order.to_dict()
        self.assertFalse(d["task_status"]["nop_tien"]["done"])
        self.assertTrue(d["nop"])               # done OR skip -> mirror True

    def test_mark_task_with_note(self):
        order = mark_task(Order.from_dict({}), "giao_hang", 5, done=True, skip=False, note="gấp", now_iso=NOW)
        self.assertEqual(order.to_dict()["task_status"]["giao_hang"]["note"], "gấp")

    def test_mark_task_preserves_existing_fields(self):
        order = mark_task(Order.from_dict({"khach_hang": "Tú", "invoice": [{"ma": "SP1"}]}),
                          "ban_hd", 1, done=True, skip=False, note="", now_iso=NOW)
        d = order.to_dict()
        self.assertEqual(d["khach_hang"], "Tú")
        self.assertEqual(d["invoice"], [{"ma": "SP1"}])

    def test_mark_all_steps_sets_done_flag(self):
        order = Order.from_dict({})
        for step in ["ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"]:
            mark_task(order, step, 1, done=True, skip=False, note="", now_iso=NOW)
        self.assertTrue(order.to_dict()["done_after_20250124"])

    def test_clear_task_removes_and_unsets_mirror(self):
        order = mark_task(Order.from_dict({}), "giao_hang", 7, done=True, skip=False, note="", now_iso=NOW)
        clear_task(order, "giao_hang")
        d = order.to_dict()
        self.assertNotIn("giao_hang", d.get("task_status", {}))
        self.assertFalse(d["giao"])

    def test_clear_last_task_removes_task_status_key(self):
        order = mark_task(Order.from_dict({}), "soan_hang", 1, done=True, skip=False, note="", now_iso=NOW)
        clear_task(order, "soan_hang")
        self.assertNotIn("task_status", order.to_dict())      # empty -> key removed

    def test_all_steps_done_predicate(self):
        done = {s: {"done": True} for s in ["ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"]}
        self.assertTrue(all_steps_done(done))
        done["nhan_tien"] = {"done": False, "skip": True}     # skip counts
        self.assertTrue(all_steps_done(done))
        done["ban_hd"] = {"done": False}
        self.assertFalse(all_steps_done(done))


if __name__ == "__main__":
    unittest.main()


class MissingCustomLabels(unittest.TestCase):
    """missing_custom_labels — dedupe việc mặc định của khách vs custom_tasks đơn."""

    def _order(self, labels):
        return Order.from_dict({
            "custom_tasks": [{"id": f"custom_{i}", "label": lb} for i, lb in enumerate(labels, 1)]
        })

    def test_empty_order_returns_all(self):
        from order_store.domain import missing_custom_labels
        self.assertEqual(missing_custom_labels(Order.from_dict({}), ["Gọi trước", "Chụp ảnh"]),
                         ["Gọi trước", "Chụp ảnh"])

    def test_existing_labels_skipped_case_insensitive(self):
        from order_store.domain import missing_custom_labels
        order = self._order(["gọi trước"])
        self.assertEqual(missing_custom_labels(order, ["Gọi Trước", "Chụp ảnh"]), ["Chụp ảnh"])

    def test_duplicate_input_labels_collapse(self):
        from order_store.domain import missing_custom_labels
        self.assertEqual(missing_custom_labels(Order.from_dict({}), ["A", "a ", " A"]), ["A"])

    def test_blank_and_none_ignored(self):
        from order_store.domain import missing_custom_labels
        self.assertEqual(missing_custom_labels(Order.from_dict({}), ["", None, "  ", "X"]), ["X"])
