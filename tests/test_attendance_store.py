"""Test chấm công (attendance_store): validate batch collector, insert idempotent
theo event_id, map mã NV → thợ + backfill, so bearer token constant-time."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone

import attendance_store
from attendance_store.domain import validate_batch, token_ok
from utils.db import get_connection
from worker_store import add_worker, ensure_table

MACHINES = {"ronald-jack-main-office"}
NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def _event(i=0, **kw):
    ev = {
        "event_id": f"{i:064x}",
        "machine_id": "ronald-jack-main-office",
        "employee_code": "11",
        "occurred_at": "2026-07-19T06:56:08+07:00",
        "timezone": "Asia/Bangkok",
        "verify_mode": 15, "in_out_mode": 0, "work_code": 0, "source_index": 9684,
        "collected_at": "2026-07-19T07:15:00Z",
    }
    ev.update(kw)
    return ev


def _batch(events):
    return {"schema_version": 1, "machine_id": "ronald-jack-main-office", "events": events}


class DomainTest(unittest.TestCase):
    def test_valid_batch(self):
        events, err = validate_batch(_batch([_event(1), _event(2)]), MACHINES, now=NOW)
        self.assertIsNone(err)
        self.assertEqual(events[0]["occurred_ymd"], "2026-07-19")

    def test_rejects_bad_schema_machine_events(self):
        self.assertIsNotNone(validate_batch({"schema_version": 2}, MACHINES, now=NOW)[1])
        self.assertIsNotNone(validate_batch(_batch([]) | {"machine_id": "x"}, MACHINES, now=NOW)[1])
        self.assertIsNotNone(validate_batch(_batch([]), MACHINES, now=NOW)[1])
        self.assertIsNotNone(validate_batch("nope", MACHINES, now=NOW)[1])

    def test_rejects_bad_event(self):
        for bad in (
            _event(1, event_id="xyz"),
            _event(1, machine_id="rogue"),
            _event(1, employee_code=""),
            _event(1, occurred_at="2026-07-19 06:56:08"),      # naive → reject
            _event(1, occurred_at="1969-01-01T00:00:00+07:00"),  # out of range
            _event(1, occurred_at="2027-12-31T00:00:00+07:00"),  # tương lai xa
            _event(1, verify_mode="fp"),
        ):
            _, err = validate_batch(_batch([bad]), MACHINES, now=NOW)
            self.assertIsNotNone(err, bad)

    def test_rejects_duplicate_in_batch(self):
        _, err = validate_batch(_batch([_event(1), _event(1)]), MACHINES, now=NOW)
        self.assertIn("duplicate", err)

    def test_token_ok(self):
        self.assertTrue(token_ok("secret", "secret"))
        self.assertFalse(token_ok("secret", "wrong"))
        self.assertFalse(token_ok("", ""))       # chưa cấu hình → đóng
        self.assertFalse(token_ok("secret", ""))


class StoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        ensure_table(self.conn)
        attendance_store.ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _validated(self, events):
        out, err = validate_batch(_batch(events), MACHINES, now=NOW)
        assert err is None, err
        return out

    def test_insert_idempotent(self):
        events = self._validated([_event(1), _event(2)])
        r1 = attendance_store.insert_events(self.conn, events)
        self.assertEqual(r1, {"accepted": 2, "duplicates": 0})
        r2 = attendance_store.insert_events(self.conn, events)   # retry của collector
        self.assertEqual(r2, {"accepted": 0, "duplicates": 2})
        n = self.conn.execute("SELECT COUNT(*) FROM attendance_events").fetchone()[0]
        self.assertEqual(n, 2)

    def test_map_and_backfill(self):
        wid = add_worker(self.conn, "An")["id"]
        attendance_store.insert_events(self.conn, self._validated([_event(1)]))
        self.assertEqual(len(attendance_store.unmapped_codes(self.conn)), 1)
        updated = attendance_store.map_employee_code(self.conn, "11", wid, by="duy")
        self.assertEqual(updated, 1)
        self.assertEqual(attendance_store.unmapped_codes(self.conn), [])
        # event MỚI của mã đã map gắn worker_id ngay lúc insert
        attendance_store.insert_events(self.conn, self._validated([_event(2)]))
        rows = attendance_store.list_events(self.conn, day="2026-07-19")
        self.assertEqual({r["worker_id"] for r in rows}, {wid})
        self.assertEqual(rows[0]["worker_name"], "An")
        # gỡ map → về hàng chờ
        attendance_store.map_employee_code(self.conn, "11", None)
        self.assertEqual(len(attendance_store.unmapped_codes(self.conn)), 1)

    def test_day_summary(self):
        events = self._validated([
            _event(1, occurred_at="2026-07-19T06:56:08+07:00"),
            _event(2, occurred_at="2026-07-19T17:02:00+07:00"),
            _event(3, employee_code="12", occurred_at="2026-07-18T07:00:00+07:00"),
        ])
        attendance_store.insert_events(self.conn, events)
        days = attendance_store.day_summary(self.conn, "2026-07")
        self.assertEqual(len(days), 2)
        d19 = next(d for d in days if d["day"] == "2026-07-19")
        self.assertEqual(d19["punches"], 2)
        self.assertIn("06:56:08", d19["first"])
        self.assertIn("17:02:00", d19["last"])
        # MỌI giờ chấm trong ngày, HH:MM tăng dần (client vẽ ống ca sáng/chiều)
        self.assertEqual(d19["times"], ["06:56", "17:02"])

    def test_edits_overlay(self):
        """Sửa tay = lớp phủ: ẩn giờ máy + thêm giờ tay; raw giữ nguyên nên máy gửi
        lại (retry) không đè phần sửa."""
        events = self._validated([
            _event(1, occurred_at="2026-07-19T06:56:08+07:00"),
            _event(2, occurred_at="2026-07-19T17:02:00+07:00"),
        ])
        attendance_store.insert_events(self.conn, events)
        eid = f"{1:064x}"
        # sửa giờ 06:56 → 07:00: ẩn event máy + thêm giờ tay
        attendance_store.set_suppressed(self.conn, eid, True, by="duy")
        attendance_store.add_manual(self.conn, "11", "2026-07-19", "07:00", by="duy")
        d = attendance_store.day_summary(self.conn, "2026-07")[0]
        self.assertEqual(d["times"], ["07:00", "17:02"])
        self.assertTrue(d["edited"])
        # máy gửi LẠI đúng batch cũ → không đè phần sửa
        attendance_store.insert_events(self.conn, self._validated([
            _event(1, occurred_at="2026-07-19T06:56:08+07:00")]))
        d = attendance_store.day_summary(self.conn, "2026-07")[0]
        self.assertEqual(d["times"], ["07:00", "17:02"])
        # chi tiết popup: máy đủ 2 dòng (1 ẩn) + 1 dòng tay
        det = attendance_store.day_detail(self.conn, "11", "2026-07-19")
        self.assertEqual([m["suppressed"] for m in det["machine"]], [True, False])
        self.assertEqual(det["manual"][0]["time"], "07:00")
        # bỏ ẩn + xoá giờ tay → về nguyên trạng máy
        attendance_store.set_suppressed(self.conn, eid, False)
        attendance_store.delete_manual(self.conn, det["manual"][0]["id"])
        d = attendance_store.day_summary(self.conn, "2026-07")[0]
        self.assertEqual(d["times"], ["06:56", "17:02"])
        self.assertFalse(d["edited"])
        # validate: giờ xấu / event không tồn tại bị chặn
        with self.assertRaises(ValueError):
            attendance_store.add_manual(self.conn, "11", "2026-07-19", "25:00")
        with self.assertRaises(ValueError):
            attendance_store.set_suppressed(self.conn, "f" * 64, True)

    def test_manual_only_day_creates_row(self):
        """Ngày chỉ có giờ tay (máy hỏng/quên) vẫn ra dòng trong summary, map tên thợ."""
        wid = add_worker(self.conn, "An")["id"]
        attendance_store.map_employee_code(self.conn, "11", wid)
        attendance_store.add_manual(self.conn, "11", "2026-07-20", "07:05")
        rows = attendance_store.day_summary(self.conn, "2026-07")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["worker_name"], "An")
        self.assertEqual(rows[0]["times"], ["07:05"])
        self.assertTrue(rows[0]["edited"])


if __name__ == "__main__":
    unittest.main()


class WorkStatsTest(unittest.TestCase):
    """Quy giờ chấm → công + tăng ca (luật: grace 15ph, bỏ xuyên trưa, bỏ trước 7h)."""

    def _ws(self, times):
        from attendance_store.domain import work_stats
        return work_stats(times)

    def test_full_day(self):
        self.assertEqual(self._ws(["07:00", "11:00", "13:00", "17:00"]), (480, 0))

    def test_partial_and_late_within_grace(self):
        # ra 17:10 (≤15ph) → không tăng ca; sáng làm 3 tiếng
        self.assertEqual(self._ws(["08:00", "11:00", "13:00", "17:10"]), (420, 0))

    def test_evening_overtime(self):
        # ra 19:00 → TC 17:00→19:00 = 120ph
        self.assertEqual(self._ws(["07:00", "11:00", "13:00", "19:00"]), (480, 120))

    def test_lunch_overtime_and_cross(self):
        # ra 11:40 → TC 40ph; còn xuyên trưa 7:00→17:00 (2 lần) → KHÔNG TC trưa
        self.assertEqual(self._ws(["07:00", "11:40"]), (240, 40))
        self.assertEqual(self._ws(["07:00", "17:00"]), (480, 0))

    def test_early_morning_not_ot(self):
        self.assertEqual(self._ws(["06:30", "11:00"]), (240, 0))

    def test_odd_punch_ignored(self):
        # lần lẻ cuối bỏ, không đoán
        self.assertEqual(self._ws(["07:00", "11:00", "13:00"]), (240, 0))
