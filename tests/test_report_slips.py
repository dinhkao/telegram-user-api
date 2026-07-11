"""Phiếu báo cáo SX (production_store.report_slips) — CRUD validate + tiền báo cáo.

Money math characterized: tiền = cây × đơn giá + phụ cấp; phụ cấp cộng ĐÚNG 1 lần
cho mỗi (phiếu, thợ) kể cả khi thợ có nhiều dòng SP trong phiếu.
"""
import sqlite3

import pytest

from production_store import report_slips
from production_store.allowances import ensure_schema as ensure_allowances


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE production_report_rows ("
        " thread_id INTEGER, report_ymd TEXT, worker_id INTEGER, worker_name TEXT,"
        " product_id INTEGER, product_code TEXT, tong_calc REAL)"
    )
    c.execute("CREATE TABLE production_workers (id INTEGER PRIMARY KEY, name TEXT)")
    c.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, code TEXT)")
    ensure_allowances(c)
    report_slips.ensure_table(c)
    yield c
    c.close()


def test_add_slip_validates(conn):
    with pytest.raises(ValueError):
        report_slips.add_slip(conn, "", "2026-07-10")
    with pytest.raises(ValueError):
        report_slips.add_slip(conn, "2026-07-11", "2026-07-10")
    s = report_slips.add_slip(conn, "2026-07-06", "2026-07-12", note="tuần 28", by="duy")
    assert s["from_ymd"] == "2026-07-06" and s["to_ymd"] == "2026-07-12"
    assert report_slips.get_slip(conn, s["id"])["note"] == "tuần 28"
    assert len(report_slips.list_slips(conn)) == 1
    assert report_slips.delete_slip(conn, s["id"]) is True
    assert report_slips.list_slips(conn) == []


def _seed(conn):
    rows = [
        # phiếu 100 (2026-07-07): Hiền 10 cây K1, Mai 5 cây K1
        (100, "2026-07-07", None, "Hiền", None, "K1", 10),
        (100, "2026-07-07", None, "Mai", None, "K1", 5),
        # phiếu 200 (2026-07-08): Hiền 2 dòng SP (K1 + K2) — phụ cấp chỉ cộng 1 lần
        (200, "2026-07-08", None, "Hiền", None, "K1", 4),
        (200, "2026-07-08", None, "Hiền", None, "K2", 6),
        # ngoài khoảng — không được tính
        (300, "2026-06-30", None, "Hiền", None, "K1", 99),
    ]
    conn.executemany("INSERT INTO production_report_rows VALUES (?,?,?,?,?,?,?)", rows)
    conn.execute("INSERT INTO production_allowances (thread_id, worker_name, amount) VALUES (200, 'Hiền', 5000)")


def test_compute_range_report_money(conn, monkeypatch):
    from production_store import wages
    monkeypatch.setattr(wages, "_cache", {"K1": {"luong": 1000}, "K2": {"luong": 2000}})
    _seed(conn)

    rep = report_slips.compute_range_report(conn, "2026-07-06", "2026-07-12")

    # Theo thợ: Hiền = 10×1000 + 4×1000 + 6×2000 + PC 5000 = 31000; Mai = 5000
    workers = {w["name"]: w for w in rep["workers"]}
    assert workers["Hiền"]["cay"] == 20 and workers["Hiền"]["money"] == 31000
    assert workers["Hiền"]["allowance"] == 5000
    assert workers["Mai"]["money"] == 5000

    # Từng phiếu SX: 100 = 15000; 200 = 4000 + 12000 + PC 5000 = 21000
    phieus = {p["thread_id"]: p for p in rep["phieus"]}
    assert phieus[100]["money"] == 15000 and phieus[100]["workers"] == 2
    assert phieus[200]["money"] == 21000 and sorted(phieus[200]["codes"]) == ["K1", "K2"]
    assert 300 not in phieus   # ngoài khoảng

    # Tổng cộng
    assert rep["totals"]["money"] == 36000
    assert rep["totals"]["cay"] == 25
    assert rep["totals"]["allowance"] == 5000
    assert rep["missing_wage"] == []


def test_compute_missing_wage_flagged(conn, monkeypatch):
    from production_store import wages
    monkeypatch.setattr(wages, "_cache", {})
    _seed(conn)
    rep = report_slips.compute_range_report(conn, "2026-07-06", "2026-07-12")
    assert set(rep["missing_wage"]) == {"K1", "K2"}
    assert rep["totals"]["money"] == 5000   # chỉ còn phụ cấp
