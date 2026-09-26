"""Giờ bắt đầu/xong phiếu SX → "HH:MM" (production_store/time_fmt.py) + parse_report
áp luật đó + tool đồng bộ dữ liệu cũ. Bản gương client: webapp/tests/normTime.test.ts."""
import json

import pytest

from production_store.domain import parse_report
from production_store.time_fmt import is_time_ok, normalize_time, time_minutes
from tools.backfill_production_times import plan_changes

CASES = [
    ("07:00", "07:00"), ("7:04", "07:04"), ("7h", "07:00"), ("13h40", "13:40"),
    ("9h5", "09:05"), ("13g40", "13:40"), ("13h 30", "13:30"), ("15h35p", "15:35"),
    ("1415", "14:15"), ("730", "07:30"), ("10", "10:00"), ("15:00_", "15:00"),
    ("7.30", "07:30"), ("7,30", "07:30"), ("09g50", "09:50"), ("11G", "11:00"),
    # giờ 1–6 = buổi chiều viết tắt (xưởng làm 7h–18h)
    ("4h15", "16:15"), ("1", "13:00"), ("5h40", "17:40"), ("12h", "12:00"),
    ("", ""), (None, ""),
]


@pytest.mark.parametrize("raw,want", CASES)
def test_normalize_time(raw, want):
    assert normalize_time(raw) == want


@pytest.mark.parametrize("raw", ["abc", "25h", "7h75", "12345", "sáng"])
def test_unparseable_kept_raw(raw):
    assert normalize_time(raw) == raw
    assert not is_time_ok(raw)


def test_idempotent():
    for raw, _ in CASES:
        once = normalize_time(raw)
        assert normalize_time(once) == once


def test_time_minutes_sorts_by_clock():
    assert time_minutes("7h") < time_minutes("13:00") < time_minutes("4h15")
    assert time_minutes("") is None and time_minutes("xx") is None


def test_parse_report_normalizes_start_end():
    c = [""] * 20
    c[0], c[1], c[2], c[3], c[18], c[19] = "Hiền", "4", "3", "3", "7h", "4h5"
    rep = parse_report("thợ;gạch;trừ;lẻ;ghi chú\n" + ";".join(c))
    assert (rep["start"], rep["end"]) == ("07:00", "16:05")


def test_backfill_plan():
    rows = [
        (1, json.dumps({"start": "7h", "end": "11g5", "rows": [1]})),
        (2, json.dumps({"start": "07:00", "end": "11:00"})),
        (3, json.dumps({"start": "sáng", "end": None})),
    ]
    changes, bad = plan_changes(rows)
    assert changes == [(1, {"start": "07:00", "end": "11:05", "rows": [1]})]
    assert bad == [(3, "start", "sáng")]
    # chạy lại trên kết quả = không đổi gì
    again, _ = plan_changes([(t, json.dumps(b)) for t, b in changes])
    assert again == []
