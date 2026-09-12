"""Phân loại GHI CHÚ báo cáo thợ (production_store/note_review.py) — cảnh báo ghi tay.

Luật (Duy chốt 2026-09-12 "bất cứ text nào ko fit 100% đều filter hết"): ghi chú phải
TRÙNG KHÍT một câu chuẩn của chính thợ đó mới là `khop`. Thừa chữ thì rơi vào 1 trong 4
diện cảnh báo — so_tien (có số tiền viết tay) · mot_phan (đúng từ khoá + chữ thừa; 2
loại này auto VẪN TRẢ TIỀN) · la (chữ lạ) · khac_tho (từ khoá người khác) · so_luong
(chỉ chỉnh số/giờ). CẢ 5 loại đều cảnh báo — "đưa vào hết", chỉ `khop` là sạch.
"""
import sqlite3

import pytest

from production_store.note_review import (
    KIND_AMOUNT, KIND_MATCH, KIND_OTHER, KIND_PARTIAL, KIND_QTY, KIND_UNKNOWN,
    keywords_for, note_kind, phrases_for, review_notes,
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
def test_chi_so_luong_gio(note):
    assert note_kind("Hằng", note) == KIND_QTY


def test_moi_loai_khong_trung_khit_deu_canh_bao():
    """Duy chốt 12/09: chỉ ghi chú TRÙNG KHÍT câu chuẩn mới sạch, còn lại vào hết."""
    from production_store.note_review import FLAG_KINDS
    assert set(FLAG_KINDS) == {KIND_AMOUNT, KIND_PARTIAL, KIND_UNKNOWN, KIND_OTHER, KIND_QTY}
    assert KIND_MATCH not in FLAG_KINDS


def test_so_tien_viet_tay_thang_ca_khi_khop_tu_khoa():
    """Ca nguy hiểm nhất: ghi chú KHỚP rule nên auto ghi tiền theo HẠNG, âm thầm bỏ
    qua số người ta đã viết (09/09/2026 Duy "vít 25k" → auto 31.200)."""
    assert note_kind("Duy", "vít 25k") == KIND_AMOUNT
    assert note_kind("Kim", "Vít 15k") == KIND_AMOUNT
    assert note_kind("Trân", "lựa đậu 30 nghìn") == KIND_AMOUNT   # chữ lạ + tiền
    assert note_kind("Phượng", "rắc mè 50.000") == KIND_AMOUNT    # từ khoá thợ khác + tiền


@pytest.mark.parametrize("note", [
    "vít tới 8h", "vít 30p", "Đã -1 gạch ( vít kẹo )", "4h vít kẹo (vít 1h25p)",
    "Vít kẹo ( về lúc 9h30)", "chiên đâuu",
])
def test_thua_chu_la_mot_phan_du_dung_tu_khoa(note):
    """Auto VẪN trả tiền cho mấy dòng này (từ khoá có mặt) rồi lặng lẽ bỏ phần thừa."""
    assert note_kind("Kim" if "chien" not in note and "chiên" not in note else "Kim Dung",
                     note) == KIND_PARTIAL


def test_chi_TRUNG_KHIT_cau_chuan_moi_la_khop():
    # câu chuẩn: đúng từ khoá HOẶC dạng đầy đủ đã khai trong _PHRASES
    assert note_kind("Kim", "vít") == KIND_MATCH
    assert note_kind("Kim", "VÍT KẸO") == KIND_MATCH        # hoa/thường + dấu không tính
    assert note_kind("Kim", "  vít   kẹo  ") == KIND_MATCH  # thừa khoảng trắng vẫn khớp
    assert "vit keo" in phrases_for("Kim") and "vit" in phrases_for("Kim")
    # "vít 5 kg" KHÔNG phải câu chuẩn → dù kg không phải tiền vẫn vào diện xem lại
    assert note_kind("Kim", "vít 5 kg") == KIND_PARTIAL


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
    _row(conn, 6, "Duy", "vít 25k")          # có số tiền viết tay
    _row(conn, 8, "Kim", "vít tới 8h")       # đúng từ khoá nhưng thừa chữ
    d = review_notes(conn)
    assert d["counts"] == {KIND_MATCH: 1, KIND_OTHER: 1, KIND_QTY: 1,
                           KIND_UNKNOWN: 2, KIND_AMOUNT: 1, KIND_PARTIAL: 1}
    assert d["flagged"] == 6          # mọi dòng trừ "vít kẹo" của Kim
    # thứ tự: tiền → một phần → lạ → khác thợ → số lượng; gộp 2 phiếu của Chín 1 nhóm
    assert [(g["worker"], g["note"], g["count"], g["kind"]) for g in d["groups"]] == [
        ("Duy", "vít 25k", 1, KIND_AMOUNT),
        ("Kim", "vít tới 8h", 1, KIND_PARTIAL),
        ("Chín", "gỡ bánh", 2, KIND_UNKNOWN),
        ("Phượng", "rắc mè", 1, KIND_OTHER),
        ("Hằng", "Đã -1 mâm", 1, KIND_QTY),
    ]
    assert d["groups"][2]["rows"][0]["thread_id"] == 2   # dòng mới nhất trước


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


# ── Tick "đã xử lý" (production_note_resolved) ────────────────────────────────
def test_tick_xu_ly_go_dong_khoi_canh_bao():
    from production_store.note_resolved import mark, unmark
    conn = _db()
    _row(conn, 1, "Chín", "gỡ bánh")
    _row(conn, 2, "Chín", "gỡ bánh", ymd="2026-09-11")
    _row(conn, 5, "Phượng", "rắc mè")
    assert review_notes(conn)["flagged"] == 3

    mark(conn, [(1, "Chín", "go banh")], by="duy")      # 1 phiếu
    d = review_notes(conn)
    assert d["flagged"] == 2 and d["resolved"] == 1
    assert [(g["worker"], g["count"]) for g in d["groups"]] == [("Chín", 1), ("Phượng", 1)]

    unmark(conn, [(1, "Chín", "go banh")])
    assert review_notes(conn)["flagged"] == 3


def test_tick_ca_nhom_lay_du_dong_ke_ca_ngoai_mau():
    """Nhóm chỉ mang `sample` dòng mẫu → tick cả nhóm phải hỏi server (group_row_keys)."""
    from production_store.note_resolved import mark
    from production_store.note_review import group_row_keys
    conn = _db()
    for i in range(12):                       # 12 > sample mặc định 8
        _row(conn, 100 + i, "Chín", "gỡ bánh")
    g = review_notes(conn)["groups"][0]
    assert g["count"] == 12 and len(g["rows"]) == 8

    keys = group_row_keys(conn, "Chín", "gỡ bánh")
    assert len(keys) == 12                    # đủ 12, không phải 8
    mark(conn, keys, by="duy")
    d = review_notes(conn)
    assert d["groups"] == [] and d["flagged"] == 0 and d["resolved"] == 12


def test_tick_khong_lan_sang_phieu_khac_hay_tho_khac():
    from production_store.note_resolved import mark
    conn = _db()
    _row(conn, 1, "Chín", "gỡ bánh")
    _row(conn, 2, "Trân", "gỡ bánh")          # thợ khác, cùng chữ
    mark(conn, [(1, "Chín", "go banh")], by="duy")
    assert [g["worker"] for g in review_notes(conn)["groups"]] == ["Trân"]


def test_group_row_keys_khop_du_hoa_thuong_va_khoang_trang():
    from production_store.note_review import group_row_keys
    conn = _db()
    _row(conn, 1, "Chín", "Gỡ  Bánh")
    _row(conn, 2, "Chín", "gỡ bánh")
    assert len(group_row_keys(conn, "Chín", "gỡ bánh")) == 2
