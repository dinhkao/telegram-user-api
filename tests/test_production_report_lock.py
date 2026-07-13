import unittest
from unittest.mock import patch

from server_app import production_routes


class ProductionReportLockTest(unittest.TestCase):
    def setUp(self):
        production_routes._report_locks.clear()

    def tearDown(self):
        production_routes._report_locks.clear()

    def test_live_lock_is_kept_without_unlock_event(self):
        production_routes._report_locks[101] = {
            "user": "Lan",
            "user_key": "lan",
            "sessions": {"tab-1": 90.0, "tab-2": 95.0},
        }
        with (
            patch("server_app.production_routes.time.monotonic", return_value=100.0),
            patch("server_app.realtime.emit_report_lock") as emit,
        ):
            lock = production_routes._lock_info(101)

        self.assertEqual(lock["user"], "Lan")
        self.assertEqual(set(lock["sessions"]), {"tab-1", "tab-2"})
        emit.assert_not_called()

    def test_expired_lock_is_removed_and_broadcast(self):
        production_routes._report_locks[102] = {
            "user": "Lan",
            "user_key": "lan",
            "sessions": {"tab-1": 1.0},
        }
        with (
            patch("server_app.production_routes.time.monotonic", return_value=100.0),
            patch("server_app.realtime.emit_report_lock") as emit,
        ):
            lock = production_routes._lock_info(102)

        self.assertIsNone(lock)
        self.assertNotIn(102, production_routes._report_locks)
        emit.assert_called_once_with(102, None)

    def test_same_user_can_own_lock_from_multiple_registered_sessions(self):
        lock = {
            "user": "Lan",
            "user_key": "lan",
            "sessions": {"tab-1": 1.0, "tab-2": 1.0},
        }
        self.assertTrue(production_routes._is_lock_mine(lock, "Lan", "tab-1"))
        self.assertTrue(production_routes._is_lock_mine(lock, " lan ", "tab-2"))
        self.assertFalse(production_routes._is_lock_mine(lock, "Lan", "tab-3"))
        self.assertFalse(production_routes._is_lock_mine(lock, "Duy", "tab-1"))

    def test_expired_session_is_pruned_but_other_tab_keeps_lock(self):
        production_routes._report_locks[103] = {
            "user": "Duy",
            "user_key": "duy",
            "sessions": {"old-tab": 1.0, "live-tab": 90.0},
        }
        with (
            patch("server_app.production_routes.time.monotonic", return_value=100.0),
            patch("server_app.realtime.emit_report_lock") as emit,
        ):
            lock = production_routes._lock_info(103)

        self.assertEqual(lock["sessions"], {"live-tab": 90.0})
        emit.assert_not_called()

    def test_legacy_lock_is_migrated(self):
        production_routes._report_locks[104] = {
            "user": "Duy",
            "sid": "tab-1",
            "at": 90.0,
        }
        with patch("server_app.production_routes.time.monotonic", return_value=100.0):
            lock = production_routes._lock_info(104)

        self.assertEqual(lock["user_key"], "duy")
        self.assertEqual(lock["sessions"], {"tab-1": 90.0})


if __name__ == "__main__":
    unittest.main()
