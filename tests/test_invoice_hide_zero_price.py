"""Tuỳ chọn ẨN dòng giá 0 khi dựng HTML hoá đơn (renderers/invoice_parts).

Khoá 2 điều: (1) ẩn thì TỔNG TIỀN HÀNG không đổi — không được giấu tiền;
(2) dòng giá 0 nhưng thành tiền KHÁC 0 vẫn phải hiện.
"""
from renderers.invoice_parts import build_product_rows


def _details():
    return [
        {"productName": "Kẹo dừa", "quantity": 2, "price": 30000, "subTotal": 60000},
        {"productName": "Hàng tặng", "quantity": 5, "price": 0, "subTotal": 0},
        {"productName": "Kẹo mè", "quantity": 1, "price": 20000, "subTotal": 20000},
    ]


def test_mac_dinh_hien_du_moi_dong():
    rows, total = build_product_rows(_details())
    assert "Hàng tặng" in rows
    assert total == 80000


def test_an_dong_gia_0_va_giu_nguyen_tong():
    rows, total = build_product_rows(_details(), hide_zero_price=True)
    assert "Hàng tặng" not in rows
    assert "Kẹo dừa" in rows and "Kẹo mè" in rows
    assert total == 80000


def test_danh_lai_so_thu_tu_sau_khi_loc():
    rows, _ = build_product_rows(_details(), hide_zero_price=True)
    stt = [r.split("</td>")[0] for r in rows.split('<td class="stt">')[1:]]
    assert stt == ["1", "2"]


def test_gia_0_nhung_thanh_tien_khac_0_van_hien():
    details = [{"productName": "Phụ thu lạ", "quantity": 1, "price": 0, "subTotal": 15000}]
    rows, total = build_product_rows(details, hide_zero_price=True)
    assert "Phụ thu lạ" in rows
    assert total == 15000
