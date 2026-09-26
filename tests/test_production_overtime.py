"""TĂNG CA thợ lương SP theo giờ ghi trong phiếu SX (production_store/overtime.py) +
tiền đã gộp đúng trong compute_range_report (nguồn của bảng lương/phiếu báo cáo)."""
import json
import sqlite3

import pytest

from production_store import report_slips
from production_store.allowances import ensure_schema as ensure_allowances
from production_store.overtime import ot_money, overtime_map, slip_overtime

MON, SUN = "2026-09-21", "2026-09-20"   # thứ 2 / chủ nhật (sau mốc áp dụng 01/09)


@pytest.mark.parametrize("end,want", [
    ("17:10", 0), ("17:15", 0), ("17:20", 20), ("17:30", 30), ("18:05", 65)])
def test_threshold_1715_counts_from_1700(end, want):
    mins, _ = slip_overtime("15:50", end, int(end[:2]) * 60 + int(end[3:]), False)
    assert mins == want


def test_fraction_is_share_of_slip_time():
    # 16:30–17:30 → 30/60 thời gian phiếu nằm trong tăng ca
    assert slip_overtime("16:30", "17:30", 17 * 60 + 30, False) == (30, 0.5)
    # phiếu bắt đầu sau 17h → trọn phiếu là tăng ca
    assert slip_overtime("17:10", "17:30", 17 * 60 + 30, False) == (20, 1.0)


def test_day_level_grace_across_slips():
    times = {1: ("16:10", "17:10"), 2: ("17:10", "17:30")}
    m = overtime_map([(1, MON, "Hiền"), (2, MON, "Hiền")], times)
    assert m[(1, "Hiền")][0] == 10 and m[(2, "Hiền")][0] == 20
    # thợ chỉ có mặt ở phiếu 1 (xong 17:10) → không tăng ca
    m2 = overtime_map([(1, MON, "Mai"), (2, MON, "Hiền")], times)
    assert (1, "Mai") not in m2


def test_no_lunch_overtime_and_bad_times():
    m = overtime_map([(1, MON, "A")], {1: ("09:00", "11:40")})
    assert m == {}
    assert overtime_map([(1, MON, "A")], {1: ("", "17:40")}) == {}          # thiếu giờ bắt đầu
    assert overtime_map([(1, MON, "A")], {1: ("17:40", "17:20")}) == {}     # xong trước bắt đầu


def test_sunday_all_overtime_and_since():
    m = overtime_map([(1, SUN, "A")], {1: ("07:00", "09:00")})
    assert m[(1, "A")] == (120, 1.0)
    assert overtime_map([(1, SUN, "A")], {1: ("", "")})[(1, "A")][1] == 1.0
    # trước 01/09/2026 không áp dụng
    assert overtime_map([(1, "2026-08-31", "A")], {1: ("16:00", "18:00")}) == {}


def test_ot_money_is_20pct():
    assert ot_money(100, 1000, 0.5) == 10000   # 50 cây TC × 1000 × 20%


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE production_report_rows (thread_id INTEGER, report_ymd TEXT, worker_id INTEGER,"
              " worker_name TEXT, product_id INTEGER, product_code TEXT, tong_calc REAL, so_gio REAL)")
    c.execute("CREATE TABLE production_workers (id INTEGER PRIMARY KEY, name TEXT, hourly_rate REAL DEFAULT 0)")
    c.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, code TEXT)")
    c.execute("CREATE TABLE production_slips (thread_id INTEGER PRIMARY KEY, sp_name TEXT, luong_1sp REAL,"
              " kind TEXT, bang TEXT)")
    ensure_allowances(c)
    report_slips.ensure_table(c)
    yield c
    c.close()


def test_compute_range_report_adds_overtime(conn):
    for tid, st, en in [(1, "13:00", "16:30"), (2, "16:30", "17:30")]:
        conn.execute("INSERT INTO production_slips VALUES (?,?,?,?,?)",
                     (tid, "K1", 1000, "san_xuat", json.dumps({"start": st, "end": en})))
    conn.executemany(
        "INSERT INTO production_report_rows (thread_id, report_ymd, worker_name, product_code, tong_calc)"
        " VALUES (?,?,?,?,?)",
        [(1, MON, "Hiền", "K1", 70), (2, MON, "Hiền", "K1", 20)])
    rep = report_slips.compute_range_report(conn, MON, MON)
    w = rep["workers"][0]
    # phiếu 2: 30/60 phút là TC → 10 cây × 1000 × 20% = 2000
    assert w["ot_money"] == 2000 and w["ot_min"] == 30
    assert w["money"] == 90 * 1000 + 2000
    assert rep["totals"]["ot_money"] == 2000
    day_items = {it["thread_id"]: it for it in w["days"][0]["items"]}
    assert day_items[2]["ot_money"] == 2000 and day_items[1]["ot_money"] == 0
