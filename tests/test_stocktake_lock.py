from __future__ import annotations

import unittest
from unittest.mock import patch

from server_app import stocktake_lock


class StocktakeLockTest(unittest.TestCase):
    def setUp(self):
        stocktake_lock._locks.clear()

    def tearDown(self):
        stocktake_lock._locks.clear()

    @patch("server_app.realtime.emit_stocktake_lock")
    def test_only_one_user_holds_lock_but_their_tabs_share_it(self, _emit):
        mine, holder = stocktake_lock.acquire(10, "Lan", "may-a")
        self.assertTrue(mine)
        self.assertEqual(holder, "Lan")
        mine, holder = stocktake_lock.acquire(10, "Duy", "may-b")
        self.assertFalse(mine)
        self.assertEqual(holder, "Lan")
        # Cùng người, kể cả khác cách viết hoa và khác tab, vẫn là chính họ.
        mine, holder = stocktake_lock.acquire(10, "lan", "may-c")
        self.assertTrue(mine)
        self.assertEqual(holder, "Lan")
        self.assertEqual(stocktake_lock.held_by(10, "LAN", "may-c"), (True, "Lan"))

    @patch("server_app.realtime.emit_stocktake_lock")
    def test_heartbeat_release_and_reacquire(self, _emit):
        stocktake_lock.acquire(11, "Lan", "may-a")
        stocktake_lock.acquire(11, "Lan", "may-c")
        self.assertEqual(stocktake_lock.held_by(11, "Lan", "may-a"), (True, "Lan"))
        self.assertFalse(stocktake_lock.release(11, "Duy", "may-b"))
        # Một tab đóng không làm rơi khóa của tab còn lại cùng người.
        self.assertTrue(stocktake_lock.release(11, "Lan", "may-a"))
        self.assertEqual(stocktake_lock.held_by(11, "Lan", "may-c"), (True, "Lan"))
        self.assertEqual(stocktake_lock.acquire(11, "Duy", "may-b"), (False, "Lan"))
        self.assertTrue(stocktake_lock.release(11, "Lan", "may-c"))
        self.assertEqual(stocktake_lock.acquire(11, "Duy", "may-b"), (True, "Duy"))

    @patch("server_app.realtime.emit_stocktake_lock")
    @patch("server_app.stocktake_lock.time.monotonic")
    def test_expired_lock_is_freed(self, mono, _emit):
        mono.return_value = 100
        stocktake_lock.acquire(12, "Lan", "a")
        mono.return_value = 100 + stocktake_lock.LOCK_TTL + 1
        self.assertIsNone(stocktake_lock.lock_info(12))
        self.assertEqual(stocktake_lock.acquire(12, "Duy", "b"), (True, "Duy"))


if __name__ == "__main__":
    unittest.main()
