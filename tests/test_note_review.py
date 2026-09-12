"""Phân loại GHI CHÚ báo cáo thợ (production_store/note_review.py) — cảnh báo ghi tay.

Khoá 3 luật: ghi chú khớp từ khoá CỦA CHÍNH thợ = khớp (auto chạy đúng) · từ khoá của
người khác = khac_tho · chữ lạ = la · chỉ số lượng/giờ = so_luong (không cảnh báo).
"""
import sqlite3

import pytest

from production_store.note_review import (
    KIND_MATCH, KIND_OTHER, KIND_QTY, KIND_UNKNOWN, keywords_for, note_kind, review_notes,
)


def test_khop_tu_khoa_cua_chinh_tho():
    assert note_kind("Kim", "vít kẹo") == KIND_MATCH
    assert note_kind("Bảo Xuyên", "quậy kẹo") == KIND_MATCH
    assert note_kind("Tâm", "rắc cơm dừa") == KIND_MATCH
    assert note_kind("Kim Dung", "Chiên đậu") == KIND_MATCH


def test_nghi_luon_khop_moi_tho():
    assert note_kind("Ai Đó", "nghỉ") == KIND_MATCH
    assert "nghi" in keywords_for("Ai Đó")


def test_tu_khoa_cua_nguoi_khac():
    # "rắc mè" là từ khoá có phụ cấp (của Duy) — Phượng ghi thì auto KHÔNG áp
    assert note_kind("Phượng", "rắc mè") == KIND_OTHER
    assert note_kind("Trân", "vô kẹo") == KIND_OTHER


def test_ghi_chu_la_can_canh_bao():
    assert note_kind("Chín", "gỡ bánh") == KIND_UNKNOWN
    assert note_kind("Phượng", "Đổ kẹo ->17:20") == KIND_UNKNOWN
    assert note_kind("Trân", "Lựa đậu") == KIND_UNKNOWN


@pytest.mark.parametrize("note", ["Đã -1 mâm", "đã +1 gạch", "về 10h", "Vô 7h40", "8h", "Đã +2 cây"])
def test_chi_so_luong_gio_khong_canh_bao(note):
    assert note_kind("Hằng", note) == KIND_QTY


def test_ghi_chu_trong_khong_xet():
    assert note_kind("Kim", "") == ""
    assert note_kind("Kim", "   ") == ""


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from production_store.report_rows import ensure_report_rows_schema
    from production_store.allowances import ensure_schema
    conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, code TEXT)")
    ensure_report_rows_schema(conn)
    ensure_schema(conn)
    return conn


def _row(conn, tid, worker, note, ymd="2026-09-10", tong=10.0):
    conn.execute(
        "INSERT INTO production_report_rows (thread_id, worker_name, product_code, report_date,"
        " report_ymd, tong_calc, note) VALUES (?,?,?,?,?,?,?)",
        (tid, worker, "K2L", "10/9/2026", ymd, tong, note),
    )
    conn.commit()


def test_review_notes_gom_nhom_va_bo_qua_dong_khop():
    conn = _db()
    _row(conn, 1, "Chín", "gỡ bánh")
    _row(conn, 2, "Chín", "gỡ bánh", ymd="2026-09-11")
    _row(conn, 3, "Kim", "vít kẹo")          # khớp rule → không cảnh báo
    _row(conn, 4, "Hằng", "Đã -1 mâm")       # chỉ số lượng → không cảnh báo
    _row(conn, 5, "Phượng", "rắc mè")        # từ khoá người khác
    d = review_notes(conn)
    assert d["counts"] == {KIND_MATCH: 1, KIND_OTHER: 1, KIND_QTY: 1, KIND_UNKNOWN: 2}
    assert d["flagged"] == 3
    # nhóm "lạ" đứng trước nhóm "khác thợ"; gộp 2 phiếu của Chín làm 1 nhóm
    assert [(g["worker"], g["note"], g["count"], g["kind"]) for g in d["groups"]] == [
        ("Chín", "gỡ bánh", 2, KIND_UNKNOWN),
        ("Phượng", "rắc mè", 1, KIND_OTHER),
    ]
    assert d["groups"][0]["rows"][0]["thread_id"] == 2   # dòng mới nhất trước


def test_review_notes_gop_nhieu_dong_cung_phieu_va_dem_phu_cap():
    conn = _db()
    _row(conn, 7, "Chín", "gỡ bánh")
    _row(conn, 7, "Chín", "gỡ bánh")   # thợ 2 dòng trong CÙNG phiếu = 1 lần
    conn.execute(
        "INSERT INTO production_allowances (thread_id, worker_name, amount, updated_by)"
        " VALUES (?,?,?,?)", (7, "Chín", 50000, "duy"))
    conn.commit()
    g = review_notes(conn)["groups"][0]
    assert g["count"] == 1 and g["paid"] == 1
    assert g["rows"][0]["allowance"] == 50000 and g["rows"][0]["allow_by"] == "duy"


def test_review_notes_loc_theo_ngay():
    conn = _db()
    _row(conn, 1, "Chín", "gỡ bánh", ymd="2026-08-01")
    _row(conn, 2, "Chín", "dọn dẹp", ymd="2026-09-10")
    d = review_notes(conn, "2026-09-01", "2026-09-30")
    assert [g["note"] for g in d["groups"]] == ["dọn dẹp"]
