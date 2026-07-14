"""Đặc tả máy trạng thái tiền KÉT (cashbox_store.domain + identity) — thuần, không DB.

Bất biến số 1: với MỌI kịch bản, tổng số dư mọi két + EXTERNAL == 0 — tiền không
tự sinh/mất (mọi movement là cặp src→dst). Mỗi test = 1 kịch bản vận hành thật
của Lê Trang Phát (giao COD → nộp → nhận tiền/phiếu thu).
"""
from datetime import datetime, timedelta, timezone

from cashbox_store.domain import (EXTERNAL, aggregate_balances,
                                  derive_order_movements, is_overdue)
from cashbox_store.identity import build_canon, fold

USERS = {"duy": "Duy", "trang": "Trang", "tri": "Trí", "thao": "Thảo"}
TG = {"1809874974": "Duy", "6730500620": "Trang", "7158345531": "Trí",
      "6970077624": "Tùng"}
_VN = timezone(timedelta(hours=7))

T1, T2, T3, T4 = ("2026-07-01T02:00:00.000Z", "2026-07-01T04:00:00.000Z",
                  "2026-07-01T06:00:00.000Z", "2026-07-01T08:00:00.000Z")


def _canon():
    canon, _names = build_canon(USERS, TG)
    return canon


def _st(by, at, note=None, skip=False, done=True):
    p = {"done": done, "by": by, "at": at, "skip": skip}
    if note:
        p["note"] = note
    return p


def _pay(amount, by, at, method="Cash"):
    return {"amount": amount, "createdBy": by, "created_at": at, "method": method}


def _o(tid=100, giao=None, nop=None, payments=None):
    d = {"thread_id": tid, "created": "2026-07-01T01:00:00.000Z", "task_status": {}}
    if giao:
        d["task_status"]["giao_hang"] = giao
    if nop:
        d["task_status"]["nop_tien"] = nop
    if payments is not None:
        d["payments"] = payments
    return d


def _run(data, total):
    res = derive_order_movements(data, total, _canon())
    bal = aggregate_balances(res["moves"])
    assert sum(bal.values()) == 0, f"tiền thất thoát: {bal}"
    return res


def _pairs(res):
    return [(m["src"], m["dst"], m["amount"]) for m in res["moves"]]


class CodFlowTests:
    def test_full_flow_giao_nop_tradu_payment(self):
        # Trí giao (COD 1.050k) → nộp trả đủ → Trang tạo phiếu thu đủ.
        o = _o(giao=_st("tri", T1), nop=_st("tri", T2, note="tra_tien_mat;img:938"),
               payments=[_pay(1_050_000, "trang", T3)])
        res = _run(o, 1_050_000)
        assert _pairs(res) == [
            (EXTERNAL, "user:tri", 1_050_000),
            ("user:tri", "office", 1_050_000),
            ("office", "user:trang", 1_050_000),
        ]
        assert res["loc"] == EXTERNAL and res["remaining"] == 0

    def test_giao_chua_nop_dang_giu(self):
        o = _o(giao=_st("tri", T1))
        res = _run(o, 500_000)
        assert _pairs(res) == [(EXTERNAL, "user:tri", 500_000)]
        assert res["loc"] == "user:tri" and res["remaining"] == 500_000
        assert res["hold_since"] > 0

    def test_no_khong_ky_toa_roi_thu_mot_phan(self):
        # Báo nợ không ký toa → sau đó Duy thu 700k/1.170k → còn 470k trong két nợ.
        o = _o(giao=_st(7158345531, T1), nop=_st(7158345531, T2, note="khong_ky_toa"),
               payments=[_pay(700_000, "duy", T3)])
        res = _run(o, 1_170_000)
        assert _pairs(res) == [
            (EXTERNAL, "user:tri", 1_170_000),
            ("user:tri", "debt", 1_170_000),
            ("debt", "user:duy", 700_000),
        ]
        assert res["loc"] == "debt" and res["remaining"] == 470_000

    def test_chieu_lay_tien_van_giu(self):
        o = _o(giao=_st("thao", T1),
               nop=_st("thao", T2, note="chieu_lay_tien", done=False))
        res = _run(o, 300_000)
        assert res["loc"] == "user:thao" and res["remaining"] == 300_000
        assert res["hold_note"] == "chieu_lay_tien"

    def test_nop_khong_note_vao_ket_chua_ro(self):
        o = _o(giao=_st("tri", T1), nop=_st("duy", T2))
        res = _run(o, 400_000)
        assert _pairs(res)[-1] == ("user:tri", "unknown", 400_000)
        assert res["loc"] == "unknown"

    def test_nop_skip_vao_ket_chua_ro(self):
        o = _o(giao=_st("tri", T1), nop=_st("duy", T2, skip=True))
        res = _run(o, 400_000)
        assert _pairs(res)[-1] == ("user:tri", "unknown", 400_000)


class PaymentTests:
    def test_khach_ck_truoc_khi_giao(self):
        # Khách CK 300k trước → giao chỉ còn thu hộ 870k.
        o = _o(giao=_st("tri", T2),
               payments=[_pay(300_000, "duy", T1, method="Transfer")])
        res = _run(o, 1_170_000)
        assert _pairs(res) == [
            (EXTERNAL, "bank", 300_000),
            (EXTERNAL, "user:tri", 870_000),
        ]
        assert res["loc"] == "user:tri" and res["remaining"] == 870_000

    def test_ck_vao_ket_ngan_hang(self):
        o = _o(payments=[_pay(500_000, "trang", T1, method="Transfer")])
        res = _run(o, 500_000)
        assert _pairs(res) == [(EXTERNAL, "bank", 500_000)]
        assert res["moves"][0]["reason"] == "payment_ck"

    def test_thu_vuot_phan_con_lai(self):
        # Thu 600k cho đơn 500k đang nằm két người giao → 500k từ két + 100k từ khách.
        o = _o(giao=_st("tri", T1), payments=[_pay(600_000, "duy", T2)])
        res = _run(o, 500_000)
        assert _pairs(res) == [
            (EXTERNAL, "user:tri", 500_000),
            ("user:tri", "user:duy", 500_000),
            (EXTERNAL, "user:duy", 100_000),
        ]
        assert res["remaining"] == 0 and res["loc"] == EXTERNAL

    def test_thu_du_truoc_thi_nop_khong_chuyen_gi(self):
        # Khách trả đủ qua phiếu thu trước; nộp sau đó không còn gì để chuyển.
        o = _o(giao=_st("tri", T1), nop=_st("tri", T3, note="tra_tien_mat"),
               payments=[_pay(500_000, "duy", T2)])
        res = _run(o, 500_000)
        assert _pairs(res) == [
            (EXTERNAL, "user:tri", 500_000),
            ("user:tri", "user:duy", 500_000),
        ]
        assert res["loc"] == EXTERNAL

    def test_tm_va_auto_complete_nop_cung_giay(self):
        # Lệnh `tm` tạo payment rồi auto-đánh nop_tien CÙNG GIÂY (không note):
        # payment xử lý trước (prio) → không còn gì rơi vào két chưa rõ.
        o = _o(giao=_st("tri", T1), nop=_st(1809874974, T2),
               payments=[_pay(500_000, 1809874974, T2)])
        res = _run(o, 500_000)
        assert _pairs(res) == [
            (EXTERNAL, "user:tri", 500_000),
            ("user:tri", "user:duy", 500_000),
        ]

    def test_nhieu_phieu_thu_tung_phan(self):
        o = _o(giao=_st("tri", T1), nop=_st("tri", T2, note="co_ky_toa"),
               payments=[_pay(400_000, "trang", T3), _pay(370_000, "duy", T4)])
        res = _run(o, 770_000)
        assert _pairs(res) == [
            (EXTERNAL, "user:tri", 770_000),
            ("user:tri", "debt", 770_000),
            ("debt", "user:trang", 400_000),
            ("debt", "user:duy", 370_000),
        ]
        assert res["remaining"] == 0


class EdgeTests:
    def test_giao_skip_nop_tradu_vao_thang_van_phong(self):
        o = _o(giao=_st("tri", T1, skip=True), nop=_st("duy", T2, note="tra_tien_mat"))
        res = _run(o, 800_000)
        assert _pairs(res) == [(EXTERNAL, "office", 800_000)]
        assert res["loc"] == "office" and res["remaining"] == 800_000

    def test_don_khong_tien_khong_movement(self):
        o = _o(giao=_st("tri", T1), nop=_st("tri", T2, note="tra_tien_mat"))
        res = _run(o, 0)
        assert res["moves"] == [] and res["loc"] == EXTERNAL

    def test_payment_amount_rac_bo_qua(self):
        o = _o(payments=[{"amount": "x", "createdBy": "duy", "created_at": T1},
                         {"amount": -5, "createdBy": "duy", "created_at": T1},
                         _pay(100_000, "duy", T2)])
        res = _run(o, 100_000)
        assert _pairs(res) == [(EXTERNAL, "user:duy", 100_000)]

    def test_blob_rac_khong_no(self):
        res = _run({"thread_id": 1, "task_status": "hong", "payments": {"a": 1}}, 100)
        assert res["moves"] == []

    def test_legacy_payment_khong_timestamp_neo_sau_created(self):
        o = _o(giao=_st("tri", T2), payments=[{"amount": 200_000, "createdBy": "duy"}])
        res = _run(o, 200_000)
        # payment không có created_at → neo created+1s (TRƯỚC giao) → external→duy
        assert _pairs(res) == [(EXTERNAL, "user:duy", 200_000)]


class IdentityTests:
    def test_tg_id_ve_cung_ket_voi_username(self):
        canon = _canon()
        assert canon(7158345531) == canon("tri") == "user:tri"
        assert canon("1809874974") == canon("duy") == "user:duy"

    def test_tg_khong_co_web_user_co_ket_rieng(self):
        canon, names = build_canon(USERS, TG)
        assert canon(6970077624) == "tg:6970077624"
        assert names["tg:6970077624"] == "Tùng"

    def test_actor_rong_hoac_api_ve_chua_ro(self):
        canon = _canon()
        assert canon(None) == "unknown"
        assert canon("") == "unknown"
        assert canon("API") == "unknown"

    def test_extra_map_ep_tay(self):
        canon, _ = build_canon(USERS, {}, {"999": "thao"})
        assert canon(999) == "user:thao"

    def test_username_la_van_tach_ket_rieng(self):
        canon, names = build_canon(USERS, TG)
        assert canon("nguoi_cu") == "user:nguoi_cu"
        assert names["user:nguoi_cu"] == "nguoi_cu"

    def test_doi_ten_user_bac_cau_ve_ket_moi(self):
        # rename "tri" → "tri2" (display "Trí" giữ nguyên): blob cũ by="tri"
        # phải về cùng két với username mới, không tách két.
        canon, _ = build_canon({"tri2": "Trí", "duy": "Duy"}, TG)
        assert canon("tri") == "user:tri2"
        assert canon(7158345531) == "user:tri2"

    def test_user_disabled_van_chung_ket(self):
        # canon nhận CẢ user disabled (service truyền đủ) — khoá tài khoản
        # không được tách tiền lịch sử; đây là đặc tả cho service._build_state.
        canon, _ = build_canon(USERS, TG)
        assert canon("tri") == canon("7158345531") == "user:tri"

    def test_fold(self):
        assert fold("Trí") == "tri" and fold("Thảo") == "thao" and fold("Đạt") == "dat"


class OverdueTests:
    def _ts(self, y, mo, d, h, mi=0):
        return datetime(y, mo, d, h, mi, tzinfo=_VN).timestamp()

    def test_truoc_17h_cung_ngay_chua_qua_han(self):
        giao = self._ts(2026, 7, 1, 8)
        assert not is_overdue(giao, self._ts(2026, 7, 1, 16, 59))
        assert is_overdue(giao, self._ts(2026, 7, 1, 17, 1))

    def test_giao_sau_17h_han_hom_sau(self):
        giao = self._ts(2026, 7, 1, 18)
        assert not is_overdue(giao, self._ts(2026, 7, 2, 16, 0))
        assert is_overdue(giao, self._ts(2026, 7, 2, 17, 1))

    def test_khong_co_moc_khong_qua_han(self):
        assert not is_overdue(0.0, self._ts(2026, 7, 1, 12))
