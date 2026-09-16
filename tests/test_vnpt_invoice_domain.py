"""Test logic thuần hoá đơn nháp VNPT: validate body + prefill + cache khách."""
import pytest

from server_app.vnpt_invoice_domain import (
    build_prefill,
    discount_name,
    normalize_body,
    updated_profile,
)


def _body(**over):
    b = {
        "buyer": {"cus_name": "Cty A", "tax_code": "3901220366", "address": "1 Lê Lợi"},
        "lines": [{"name": "Kẹo X", "unit": "bịch", "qty": 2, "price": 100000, "sp_id": 7}],
        "vat_rate": 8,
    }
    b.update(over)
    return b


def test_normalize_body_ok():
    buyer, lines, rate = normalize_body(_body())
    assert buyer["cus_name"] == "Cty A"
    assert buyer["phone"] == ""          # key thiếu thành chuỗi rỗng
    assert lines[0]["sp_id"] == 7 and lines[0]["qty"] == 2.0
    assert rate == 8


def test_normalize_body_rejects():
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[]))
    with pytest.raises(ValueError):
        normalize_body(_body(vat_rate=7))
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[{"name": "", "qty": 1, "price": 1}]))
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[{"name": "A", "qty": 0, "price": 1}]))
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[{"name": "A", "qty": 1, "price": -5}]))
    with pytest.raises(ValueError):
        normalize_body(_body(buyer={}))
    # MST + tên + địa chỉ BẮT BUỘC (Duy chốt 2026-08-26)
    with pytest.raises(ValueError, match="tên đơn vị"):
        normalize_body(_body(buyer={"tax_code": "3901220366", "address": "x"}))
    with pytest.raises(ValueError, match="địa chỉ"):
        normalize_body(_body(buyer={"cus_name": "A", "tax_code": "3901220366"}))
    with pytest.raises(ValueError, match="mã số thuế"):
        normalize_body(_body(buyer={"cus_name": "A", "address": "x"}))
    with pytest.raises(ValueError, match="không hợp lệ"):
        normalize_body(_body(buyer={"cus_name": "A", "address": "x", "tax_code": "12ab"}))
    # sai SỐ KIỂM TRA (checksum) — VNPT sẽ bỏ trống MST kiểu này trên hoá đơn
    with pytest.raises(ValueError, match="số kiểm tra"):
        normalize_body(_body(buyer={"cus_name": "A", "address": "x", "tax_code": "0123456789"}))


def test_mst_valid_checksum():
    from server_app.vnpt_invoice_domain import mst_valid
    # 2 MST thật (Lê Trang Phát, VNPT-Vinaphone) + dạng chi nhánh -NNN
    assert mst_valid("3901220366") and mst_valid("0106869738")
    assert mst_valid("3901220366-001")
    # 12 số = SỐ ĐỊNH DANH CÁ NHÂN (CCCD, thay MST cho cá nhân từ 01/07/2025) —
    # chỉ kiểm dạng, VNPT in bình thường (thực nghiệm 2026-08-26)
    assert mst_valid("031082011991")
    assert not mst_valid("0123456789")
    assert not mst_valid("39012203")       # thiếu số
    assert not mst_valid("3901220366-01")
    assert not mst_valid("0310820119911")  # 13 số liền không phải CCCD/MST


def test_normalize_body_email():
    ok = {"cus_name": "A", "address": "x", "tax_code": "3901220366"}
    buyer, _, _ = normalize_body(_body(buyer={**ok, "email": " a@b.vn ; c@d.com "}))
    assert buyer["email"] == "a@b.vn;c@d.com"
    buyer, _, _ = normalize_body(_body(buyer=ok))
    assert buyer["email"] == ""               # email là TUỲ CHỌN
    with pytest.raises(ValueError, match="email"):
        normalize_body(_body(buyer={**ok, "email": "khong-phai-mail"}))


def test_normalize_body_mst_formats():
    for mst in ("3901220366", "3901220366-001", "39 0122 0366"):
        buyer, _, _ = normalize_body(_body(buyer={"cus_name": "A", "address": "x", "tax_code": mst}))
        assert buyer["tax_code"] == mst.replace(" ", "")


ORDER = {"invoice": [
    {"sp": "KD3", "sp_id": 7, "name": "Kẹo đậu 3kg", "sl": 3, "price": 390000},
    {"sp": "DM450", "sp_id": 10, "name": "Đậu 450g", "sl": 10, "price": 62000},
]}


def test_prefill_no_profile_uses_order_and_catalog():
    cust = {"name": "Cty B", "address": "1 Lê Lợi", "contactNumber": "090", "kh_id": 55}
    p = build_prefill(ORDER, cust, {7: "bịch", 10: "hũ"})
    assert p["buyer"]["cus_name"] == "Cty B"
    assert "cus_code" not in p["buyer"]   # mã khách hàng đã bỏ (Duy 2026-08-26)
    assert p["vat_rate"] == 8
    assert p["lines"][0] == {"name": "Kẹo đậu 3kg", "unit": "bịch", "qty": 3.0,
                             "price": 390000, "sp_id": 7}


def test_prefill_profile_overrides_name_unit_price_keeps_qty():
    cust = {
        "name": "Cty B",
        "vnpt_profile": {
            "buyer": {"cus_name": "CÔNG TY TNHH B", "tax_code": "0123"},
            "vat_rate": 10,
            "products": {"7": {"name": "Kẹo đậu phộng loại 1", "unit": "túi", "price": 400000}},
            "extra_lines": [{"name": "Phí giao", "unit": "lần", "qty": 1, "price": 30000}],
        },
    }
    p = build_prefill(ORDER, cust, {7: "bịch", 10: "hũ"})
    assert p["vat_rate"] == 10
    assert p["buyer"]["cus_name"] == "CÔNG TY TNHH B"
    ln = p["lines"][0]
    assert ln["name"] == "Kẹo đậu phộng loại 1" and ln["unit"] == "túi"
    assert ln["price"] == 400000
    assert ln["qty"] == 3.0                      # SL luôn theo ĐƠN hiện tại
    assert p["lines"][1]["name"] == "Đậu 450g"   # SP chưa có template → theo đơn
    assert p["lines"][2]["name"] == "Phí giao"   # dòng thêm tay lần trước quay lại


def test_updated_profile_merges_products_replaces_extras():
    old = {"products": {"9": {"name": "Cũ", "unit": "kg", "price": 1}},
           "extra_lines": [{"name": "Cũ extra", "qty": 2, "price": 5}]}
    buyer = {"cus_name": "X"}
    lines = [
        {"name": "Kẹo mới", "unit": "túi", "qty": 3, "price": 400000, "sp_id": 7},
        {"name": "Phí giao", "unit": "lần", "qty": 1, "price": 30000},
    ]
    prof = updated_profile(old, buyer, lines, 10)
    assert prof["products"]["9"]["name"] == "Cũ"          # giữ template SP cũ
    assert prof["products"]["7"]["price"] == 400000
    assert prof["extra_lines"] == [{"name": "Phí giao", "unit": "lần",
                                    "price": 30000, "qty": 1.0}]
    assert prof["vat_rate"] == 10 and prof["buyer"] == buyer


def test_normalize_body_discount_line():
    body = _body(lines=[
        {"name": "Kẹo X", "unit": "bịch", "qty": 2, "price": 100000, "sp_id": 7},
        # dòng CK: client gửi price (hoặc amount) = số tiền, qty/unit bỏ qua
        {"name": "Chiết khấu", "kind": "chiet_khau", "price": 50000, "qty": 9, "unit": "xx", "sp_id": 7},
    ])
    _, lines, _ = normalize_body(body)
    ck = lines[1]
    assert ck == {"name": "Chiết khấu", "unit": "", "qty": 1.0, "price": 50000, "kind": "chiet_khau"}
    # nhận cả key amount
    body["lines"][1] = {"name": "CK", "kind": "chiet_khau", "amount": 1000}
    assert normalize_body(body)[1][1]["price"] == 1000


def test_normalize_body_discount_rejects():
    with pytest.raises(ValueError):          # CK ≤ 0
        normalize_body(_body(lines=[{"name": "A", "qty": 1, "price": 100},
                                    {"name": "CK", "kind": "chiet_khau", "price": 0}]))
    with pytest.raises(ValueError):          # chỉ toàn CK
        normalize_body(_body(lines=[{"name": "CK", "kind": "chiet_khau", "price": 5}]))
    with pytest.raises(ValueError):          # CK vượt tiền hàng
        normalize_body(_body(lines=[{"name": "A", "qty": 1, "price": 100},
                                    {"name": "CK", "kind": "chiet_khau", "price": 101}]))


def test_profile_keeps_discount_line_as_extra():
    lines = [
        {"name": "Kẹo", "unit": "bịch", "qty": 2.0, "price": 1000, "sp_id": 7},
        {"name": "CK khách quen", "unit": "", "qty": 1.0, "price": 500, "kind": "chiet_khau"},
    ]
    prof = updated_profile(None, {"cus_name": "C"}, lines, 8)
    assert prof["products"] == {"7": {"name": "Kẹo", "unit": "bịch", "price": 1000}}
    assert prof["extra_lines"] == [{"name": "CK khách quen", "unit": "", "price": 500,
                                    "qty": 1.0, "kind": "chiet_khau"}]
    # lần sau prefill: dòng CK điền lại kèm kind
    pre = build_prefill({"invoice": [{"sp_id": 7, "sp": "K", "sl": 3, "price": 900}]},
                        {"vnpt_profile": prof}, {})
    assert pre["lines"][-1]["kind"] == "chiet_khau" and pre["lines"][-1]["price"] == 500


def test_discount_name_format():
    assert discount_name(5, 1401250) == "Chiết khấu thương mại 5%, số tiền 1.401.250 đồng"
    assert discount_name(2.5, 900) == "Chiết khấu thương mại 2,5%, số tiền 900 đồng"


def test_normalize_body_discount_percent():
    body = _body(lines=[
        {"name": "A", "unit": "bịch", "qty": 10, "price": 100000},
        {"name": "B", "unit": "hũ", "qty": 5, "price": 80250},        # tổng hàng 1.401.250
        {"name": "gõ gì cũng bị đè", "kind": "chiet_khau", "pct": "5", "price": 1},
    ])
    _, lines, _ = normalize_body(body)
    ck = lines[2]
    assert ck["pct"] == 5.0 and ck["price"] == 70063          # 70062.5 → làm tròn lên
    assert ck["name"] == "Chiết khấu thương mại 5%, số tiền 70.063 đồng"
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[{"name": "A", "qty": 1, "price": 100},
                                    {"name": "CK", "kind": "chiet_khau", "pct": 101}]))


def test_profile_discount_percent_recomputed_on_prefill():
    lines = [{"name": "Kẹo", "unit": "bịch", "qty": 2.0, "price": 1000, "sp_id": 7},
             {"name": "x", "unit": "", "qty": 1.0, "price": 100, "kind": "chiet_khau", "pct": 5.0}]
    prof = updated_profile(None, {"cus_name": "C"}, lines, 8)
    assert prof["extra_lines"][0]["pct"] == 5.0
    pre = build_prefill({"invoice": [{"sp_id": 7, "sp": "K", "sl": 3, "price": 900}]},
                        {"vnpt_profile": prof}, {})
    ck = pre["lines"][-1]
    # 5% × (3 × 1000): SL theo đơn mới, giá theo template hồ sơ khách
    assert ck["pct"] == 5.0 and ck["price"] == 150
    assert ck["name"] == "Chiết khấu thương mại 5%, số tiền 150 đồng"


def test_reset_roundtrip_gives_identical_draft():
    """RESET (POST .../vnpt-invoice/reset) đẩy lại chính nội dung ĐANG LƯU qua
    normalize_body → phải ra hoá đơn Y HỆT. Blob lưu `lines` = totals["lines"]
    (đã kèm `amount`, dòng CK theo % đã có tiền + tên tự sinh) nên đây là chỗ dễ
    lệch nhất: `amount` thừa, `pct` rơi mất, hay CK bị tính 2 lần."""
    from integrations.vnpt_invoice import compute_totals

    buyer, lines, vat = normalize_body(_body(
        buyer={"cus_name": "Cty A", "tax_code": "3901220366", "address": "1 Lê Lợi",
               "email": "a@b.vn;c@d.vn", "payment_method": "TM/CK"},
        lines=[
            {"name": "Kẹo X", "unit": "bịch", "qty": 2.5, "price": 100000, "sp_id": 7},
            {"name": "Kẹo Y", "unit": "hũ", "qty": 3, "price": 62000},
            {"name": "CK", "kind": "chiet_khau", "pct": 5},
        ]))
    stored = compute_totals(lines, vat)          # đúng thứ đang nằm trong blob đơn

    buyer2, lines2, vat2 = normalize_body(
        {"buyer": buyer, "lines": stored["lines"], "vat_rate": vat})
    again = compute_totals(lines2, vat2)

    assert (buyer2, vat2) == (buyer, vat)
    assert again == stored                        # từng đồng, từng dòng, kể cả CK
