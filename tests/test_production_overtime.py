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


def test_ot_toggle_off_per_worker(conn):
    from production_store.overtime_off import off_keys, set_ot_enabled
    conn.execute("INSERT INTO production_slips VALUES (?,?,?,?,?)",
                 (2, "K1", 1000, "san_xuat", json.dumps({"start": "16:30", "end": "17:30"})))
    conn.executemany(
        "INSERT INTO production_report_rows (thread_id, report_ymd, worker_name, product_code, tong_calc)"
        " VALUES (?,?,?,?,?)", [(2, MON, "Hiền", "K1", 20), (2, MON, "Mai", "K1", 20)])
    # mặc định BẬT cho cả 2
    rep = report_slips.compute_range_report(conn, MON, MON)
    assert {w["name"]: w["ot_money"] for w in rep["workers"]} == {"Hiền": 2000, "Mai": 2000}
    # tắt riêng Mai (khác hoa thường vẫn khớp) → chỉ Mai mất tăng ca
    set_ot_enabled(conn, 2, "mai", False, by="duy")
    assert off_keys(conn, [2]) == {(2, "mai")}
    rep = report_slips.compute_range_report(conn, MON, MON)
    ws = {w["name"]: w for w in rep["workers"]}
    assert ws["Mai"]["ot_money"] == 0 and ws["Mai"]["money"] == 20000
    assert ws["Hiền"]["ot_money"] == 2000
    # bật lại — gọi 2 lần vẫn đúng 1 trạng thái
    set_ot_enabled(conn, 2, "Mai", True)
    set_ot_enabled(conn, 2, "Mai", True)
    assert off_keys(conn, [2]) == set()


def _slip(conn, tid, st, en, rows):
    """Phiếu + mirror: rows = [(thợ, cây, ghi chú)]."""
    bang = {"start": st, "end": en, "product_code": "K1",
            "rows": [{"name": n, "tong_calc": c, "note": note} for n, c, note in rows]}
    conn.execute("INSERT OR REPLACE INTO production_slips VALUES (?,?,?,?,?)",
                 (tid, "K1", 1000, "san_xuat", json.dumps(bang)))
    conn.execute("DELETE FROM production_report_rows WHERE thread_id = ?", (tid,))
    conn.executemany(
        "INSERT INTO production_report_rows (thread_id, report_ymd, worker_name, product_code, tong_calc)"
        " VALUES (?,?,?,?,?)", [(tid, MON, n, "K1", c) for n, c, _ in rows])
    return bang


def _allow(conn, tid):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT worker_name, amount FROM production_allowances WHERE thread_id = ?", (tid,))}


def test_auto_allowance_uses_money_after_overtime(conn):
    from production_store.allowance_auto import apply_auto_allowances
    # 16:30–17:30 → 50% thời gian là TC: Hiền 100 cây = 100.000 + 10.000 phụ trội
    bang = _slip(conn, 2, "16:30", "17:30", [("Hiền", 100, ""), ("Kim", 0, "vít kẹo")])
    apply_auto_allowances(conn, 2, bang)
    assert _allow(conn, 2) == {"Kim": 110_000}


def test_auto_allowance_follows_ot_toggle_and_same_day_slip(conn):
    from production_store.allowance_auto import apply_auto_allowances, reapply_slip
    from production_store.overtime_off import set_ot_enabled
    # phiếu 1 kết thúc 17:10 (chưa quá 17:15) → chưa có TC
    b1 = _slip(conn, 1, "16:10", "17:10", [("Hiền", 60, ""), ("Kim", 0, "vít")])
    apply_auto_allowances(conn, 1, b1)
    assert _allow(conn, 1) == {"Kim": 60_000}
    # phiếu 2 cùng ngày kéo Hiền tới 17:30 → phiếu 1 có 10' TC (1/6) → +2.000
    _slip(conn, 2, "17:10", "17:30", [("Hiền", 20, "")])
    reapply_slip(conn, 1)
    assert _allow(conn, 1) == {"Kim": 62_000}
    # văn phòng tắt TC của Hiền ở phiếu 1 → mốc về lại số không TC
    set_ot_enabled(conn, 1, "Hiền", False)
    reapply_slip(conn, 1)
    assert _allow(conn, 1) == {"Kim": 60_000}
