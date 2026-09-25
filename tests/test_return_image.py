"""renderers/phieu_tra_hang — HTML hoá đơn trả hàng (thuần, không DB/Playwright)."""
from renderers.phieu_tra_hang import _date_str, generate_return_html, return_summary

_ITEMS = [{"sp": "K10LV87", "name": "Kẹo 10m lớn", "sl": 50.0, "price": 17000.0},
          {"sp": "KDBN1L", "sl": 2.5, "price": 23000.0}]


def test_draft_has_only_total_and_draft_label():
    slip = {"id": 15, "items": _ITEMS, "total": 907500, "created_at": "2026-09-25T07:59:56+07:00"}
    assert return_summary(slip) == [("Tổng tiền hàng trả", "-907,500")]
    html = generate_return_html(slip, "Sạp 7 ngân")
    assert "HÓA ĐƠN TRẢ HÀNG" in html and "Phiếu trả #15 (nháp)" in html
    assert "Nợ trước" not in html
    assert "07:59 25/09/2026" in html
    # tên hiện hành nếu có, không thì mã; SL lẻ kiểu VN; thành tiền = giá × SL
    assert "Kẹo 10m lớn" in html and ">KDBN1L<" in html
    assert ">2,5<" in html and "57,500" in html


def test_invoiced_shows_debt_chain_from_debt_before():
    slip = {"id": 14, "items": _ITEMS[:1], "total": 850000, "kv_invoice_id": 1,
            "kv_invoice_code": "HD087196", "debt_before": 29440000, "debt_after": 1}
    rows = dict(return_summary(slip))
    assert rows["Tổng tiền hàng trả"] == "-850,000"
    assert rows["Nợ trước"] == "29,440,000"
    assert rows["Trừ hàng trả"] == "-850,000"
    assert rows["Còn nợ"] == "28,590,000"      # nợ trước − tổng, không dùng debt_after
    assert "HD087196" in generate_return_html(slip, "")


def test_invoiced_without_debt_before_and_escaping():
    slip = {"id": 1, "items": [{"sp": "X", "name": "<b>", "sl": 1, "price": 1}], "total": 1,
            "kv_invoice_id": 2, "kv_invoice_code": "HD1", "note": "a<b"}
    assert [r[0] for r in return_summary(slip)] == ["Tổng tiền hàng trả"]
    html = generate_return_html(slip, "A & B")
    assert "&lt;b&gt;" in html and "A &amp; B" in html and "a&lt;b" in html
    assert "KH: A &amp; B" in html


def test_date_str_sqlite_utc_and_bad():
    assert _date_str("2026-09-25 00:59:56") == "07:59 25/09/2026"
    assert _date_str("") == "" and _date_str("xx") == ""
