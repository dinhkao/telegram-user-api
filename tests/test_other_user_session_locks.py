import json
import unittest
from unittest.mock import patch

from server_app import invoice_edit_lock, stock_pick_lock


class _Request(dict):
    def __init__(self, thread_id: int, body: dict):
        super().__init__()
        self.match_info = {"thread_id": str(thread_id)}
        self._body = body

    async def json(self):
        return self._body


def _payload(response):
    return json.loads(response.text)


class InvoiceEditSessionLockTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        invoice_edit_lock._edit_locks.clear()

    def tearDown(self):
        invoice_edit_lock._edit_locks.clear()

    async def test_same_user_has_multiple_tabs_and_each_releases_only_itself(self):
        with patch("server_app.realtime.emit_invoice_edit_lock") as emit:
            first = await invoice_edit_lock.invoice_edit_lock_handler(
                _Request(10, {"user": "Duy", "sid": "tab-1"})
            )
            second = await invoice_edit_lock.invoice_edit_lock_handler(
                _Request(10, {"user": " duy ", "sid": "tab-2"})
            )
            other = await invoice_edit_lock.invoice_edit_lock_handler(
                _Request(10, {"user": "Lan", "sid": "tab-3"})
            )

            self.assertTrue(_payload(first)["mine"])
            self.assertTrue(_payload(second)["mine"])
            self.assertFalse(_payload(other)["mine"])
            self.assertEqual(set(invoice_edit_lock._edit_locks[10]["sessions"]), {"tab-1", "tab-2"})

            await invoice_edit_lock.invoice_edit_unlock_handler(
                _Request(10, {"user": "Duy", "sid": "tab-1"})
            )
            self.assertIn(10, invoice_edit_lock._edit_locks)
            self.assertEqual(set(invoice_edit_lock._edit_locks[10]["sessions"]), {"tab-2"})

            await invoice_edit_lock.invoice_edit_unlock_handler(
                _Request(10, {"user": "Duy", "sid": "tab-2"})
            )
            self.assertNotIn(10, invoice_edit_lock._edit_locks)
            self.assertEqual(emit.call_count, 2)


class StockPickSessionLockTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        stock_pick_lock._pick_locks.clear()

    def tearDown(self):
        stock_pick_lock._pick_locks.clear()

    async def test_same_user_tabs_share_product_lock_without_early_release(self):
        with patch("server_app.realtime.emit_stock_pick_lock") as emit:
            first = await stock_pick_lock.stock_pick_lock_handler(
                _Request(20, {"user": "Duy", "code": "k2l", "sid": "tab-1"})
            )
            second = await stock_pick_lock.stock_pick_lock_handler(
                _Request(20, {"user": "Duy", "code": "K2L", "sid": "tab-2"})
            )
            other = await stock_pick_lock.stock_pick_lock_handler(
                _Request(20, {"user": "Lan", "code": "K2L", "sid": "tab-3"})
            )

            self.assertTrue(_payload(first)["mine"])
            self.assertTrue(_payload(second)["mine"])
            self.assertFalse(_payload(other)["mine"])
            key = stock_pick_lock._key(20, "K2L")
            self.assertEqual(set(stock_pick_lock._pick_locks[key]["sessions"]), {"tab-1", "tab-2"})

            await stock_pick_lock.stock_pick_unlock_handler(
                _Request(20, {"user": "Duy", "code": "K2L", "sid": "tab-1"})
            )
            self.assertIn(key, stock_pick_lock._pick_locks)

            await stock_pick_lock.stock_pick_unlock_handler(
                _Request(20, {"user": "Duy", "code": "K2L", "sid": "tab-2"})
            )
            self.assertNotIn(key, stock_pick_lock._pick_locks)
            self.assertEqual(emit.call_count, 2)


if __name__ == "__main__":
    unittest.main()
