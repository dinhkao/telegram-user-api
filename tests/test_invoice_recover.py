"""Dò HĐ KiotViet 'mồ côi' sau khi POST /invoices timeout.

Bối cảnh thật (2026-08-09): HD085869 được KiotViet tạo lúc 16:16:02 nhưng
response không về trong 30s → đơn 503268 không có kiotvietInvoiceID, bấm lại là
tạo HĐ trùng. Test khoá luật CHỌN: đúng thời điểm + đúng từng dòng + chưa gắn đơn.
"""
from datetime import datetime

from integrations.kiotviet.recover import details_match, parse_kv_time, pick_orphan

SINCE = datetime(2026, 8, 9, 16, 15, 30)
SENT = [
    {"productId": 34, "quantity": 50, "price": 16000},
    {"productCode": "K2NV120", "quantity": 20, "price": 7000},
]


def _inv(inv_id, created, details, code="HD1"):
    return {"id": inv_id, "code": code, "createdDate": created, "invoiceDetails": details}


def _got(details):
    """Dòng KiotViet trả về luôn có CẢ productId lẫn productCode."""
    out = []
    for d in details:
        out.append({"productId": d.get("productId") or 999, "productCode": d.get("productCode") or "XX",
                    "quantity": d["quantity"], "price": d["price"]})
    return out


def test_parse_kv_time_7_chu_so_phan_giay():
    assert parse_kv_time("2026-08-09T16:16:02.3830000") == datetime(2026, 8, 9, 16, 16, 2, 383000)
    assert parse_kv_time("") is None
    assert parse_kv_time("rác") is None


def test_khop_khong_phu_thuoc_thu_tu_dong():
    got = _got(SENT)[::-1]
    assert details_match(SENT, got)


def test_lech_so_luong_hoac_gia_thi_khong_khop():
    got = _got(SENT)
    got[0]["quantity"] = 49
    assert not details_match(SENT, got)
    got = _got(SENT)
    got[1]["price"] = 7500
    assert not details_match(SENT, got)


def test_thieu_hoac_thua_dong_thi_khong_khop():
    assert not details_match(SENT, _got(SENT)[:1])
    assert not details_match(SENT, _got(SENT) + _got(SENT[:1]))


def test_nhan_dung_hd_mo_coi():
    inv = _inv(271414758, "2026-08-09T16:16:02.3830000", _got(SENT), "HD085869")
    assert pick_orphan([inv], sent_details=SENT, since=SINCE) is inv


def test_bo_qua_hd_tao_truoc_moc():
    inv = _inv(1, "2026-08-09T16:14:57.1770000", _got(SENT))
    assert pick_orphan([inv], sent_details=SENT, since=SINCE) is None


def test_bo_qua_hd_da_gan_don_khac():
    inv = _inv(271414758, "2026-08-09T16:16:02.3830000", _got(SENT))
    assert pick_orphan([inv], sent_details=SENT, since=SINCE, used_ids={271414758}) is None


def test_nhieu_ung_vien_lay_cai_som_nhat():
    a = _inv(2, "2026-08-09T16:16:02.0000000", _got(SENT), "SOM")
    b = _inv(3, "2026-08-09T16:17:40.0000000", _got(SENT), "MUON")
    assert pick_orphan([b, a], sent_details=SENT, since=SINCE)["code"] == "SOM"


def test_don_khac_cua_cung_khach_khong_bi_nhan_nham():
    khac = _got([{"productId": 34, "quantity": 10, "price": 16000}])
    inv = _inv(9, "2026-08-09T16:16:02.0000000", khac)
    assert pick_orphan([inv], sent_details=SENT, since=SINCE) is None
