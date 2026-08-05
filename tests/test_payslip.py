"""PHIẾU LƯƠNG THÁNG (salary_store.payslip) — dựng nội dung phiếu, thuần, không DB."""
from salary_store.payslip import build_payslip, _slots


def _row(**kw):
    r = {"worker_id": 7, "name": "Trí", "wage_type": "time", "cong": 23.6, "ot_gio": 33.5,
         "monthly_salary": 9_880_000, "luong_cong": 8_968_000, "luong_tc": 1_906_650,
         "luong_sp": 0, "pc_phieu": 0, "cc_on": True, "vs_on": True,
         "thuong_cc": 200_000, "thuong_vs": 272_308, "thuong": 0,
         "ung_manual": 10_000_000, "ung_weekly": 0, "bhxh": 20_000, "thuc_lanh": 1_326_958}
    r.update(kw)
    return r


def _labels(p):
    return [ln["label"] for ln in p["lines"]]


def test_lines_theo_dung_thu_tu_va_dau_am():
    p = build_payslip(_row(), [], [], {}, ym="2026-06", today_ymd="2026-08-05")
    lb = _labels(p)
    assert lb[:2] == ["Số ngày công", "Số giờ tăng ca"]
    assert "Lương theo ngày công" in lb and "Lương tăng ca" in lb
    # mốc lương = số nội bộ để tính ra lương ngày công, KHÔNG in lên phiếu phát cho thợ
    assert "Mốc lương tháng" not in lb
    assert lb[-1] == "THỰC NHẬN"
    by = {ln["label"]: ln for ln in p["lines"]}
    assert by["Trừ tạm ứng"]["value"] == -10_000_000      # khoản TRỪ ghi số âm
    assert by["Trừ BHXH"]["value"] == -20_000
    assert by["THỰC NHẬN"]["value"] == 1_326_958 and by["THỰC NHẬN"]["total"]
    assert p["name"] == "Trí" and p["printed"] == "05/08/2026" and p["ym_label"] == "Tháng 06/2026"


def test_tong_cac_dong_bang_dung_thuc_nhan():
    """Cộng MỌI dòng tiền (trừ dòng tổng) phải ra đúng THỰC NHẬN — phiếu in không
    được để người ta bấm máy tính ra số khác. Không còn dòng thông tin nào phải
    chừa ra kể từ khi bỏ mốc lương."""
    p = build_payslip(_row(), [{"amount": 50_000, "note": "điện thoại", "calc_label": ""}],
                      [], {}, ym="2026-06", today_ymd="2026-08-05")
    s = sum(ln["value"] for ln in p["lines"] if ln["kind"] == "money" and not ln["total"])
    assert s == 1_326_958 + 50_000
    assert p["lines"][-1]["value"] == 1_326_958


def test_tho_luong_san_pham_khong_co_dong_tang_ca():
    r = _row(wage_type="product", luong_sp=5_000_000, luong_cong=0, luong_tc=0, pc_phieu=300_000)
    lb = _labels(build_payslip(r, [], [], {}, ym="2026-06"))
    assert "Lương sản phẩm" in lb and "Lương tăng ca" not in lb and "Mốc lương tháng" not in lb
    assert "  (trong đó phụ cấp phiếu SX)" in lb


def test_time_flat_gop_tang_ca_vao_ngay_cong():
    lb = _labels(build_payslip(_row(wage_type="time_flat", luong_tc=0), [], [], {}, ym="2026-06"))
    assert "Lương tăng ca" not in lb
    assert any(x.startswith("Số giờ tăng ca (đã gộp") for x in lb)


def test_phu_cap_ghi_cong_thuc_va_ung_theo_tung_lan():
    allow = [{"amount": 300_000, "note": "xăng xe", "calc_label": "10% lương gốc"}]
    adv = [{"amount": 1_000_000, "adv_date": "2026-06-01", "note": "mượn"},
           {"amount": 3_000_000, "adv_date": "2026-06-15", "note": "ứng"}]
    p = build_payslip(_row(), allow, adv, {}, ym="2026-06")
    assert "Phụ cấp xăng xe (10% lương gốc)" in _labels(p)
    assert p["advances"][0] == {"date": "01/06/2026", "amount": 1_000_000, "note": "mượn"}
    assert p["adv_total"] == 4_000_000


def test_chấm_công_du_moi_ngay_va_cong_don_dung():
    times = {"2026-06-01": ["06:52", "10:56", "12:51", "17:05"],   # 476ph công, 0 TC
             "2026-06-03": ["06:55", "10:57", "12:49", "17:36"]}   # 477ph công, 36ph TC
    p = build_payslip(_row(), [], [], times, ym="2026-06", today_ymd="2026-08-05")
    assert len(p["days"]) == 30                       # tháng cũ → đủ 30 ngày
    d1, d2 = p["days"][0], p["days"][2]
    assert d1["d"] == "01/06" and d1["dow"] == "T.2" and d1["gio"] == 7.9 and d1["tc"] == 0.0
    assert d1["slots"] == ["06:52", "10:56", "12:51", "17:05"]
    assert d2["gio"] == 8.0 and d2["tc"] == 0.6
    assert p["days"][1]["slots"] == ["", "", "", ""] and p["days"][1]["gio"] == 0
    assert p["day_total"]["gio"] == round((476 + 477) / 60, 1)
    assert p["day_total"]["tc"] == 0.6
    assert p["day_total"]["cong"] == round((476 + 477) / 480, 2)


def test_thang_dang_chay_chi_in_toi_hom_nay():
    p = build_payslip(_row(), [], [], {}, ym="2026-08", today_ymd="2026-08-05")
    assert len(p["days"]) == 5 and p["days"][-1]["d"] == "05/08"


def test_chu_nhat_danh_dau_va_toan_bo_la_tang_ca():
    times = {"2026-06-07": ["07:06", "11:12", "12:55", "16:42"]}   # 07/06/2026 = CN
    p = build_payslip(_row(), [], [], times, ym="2026-06", today_ymd="2026-08-05")
    cn = p["days"][6]
    assert cn["dow"] == "CN" and cn["sunday"] and cn["gio"] == 0.0 and cn["tc"] > 0


def test_luong_cho_hang_vao_phieu_va_vao_tong():
    """Lương chờ hàng = khoản CỘNG, phải in ra phiếu và nằm trong THỰC NHẬN."""
    r = _row(cho_hang=300_000, thuc_lanh=1_326_958 + 300_000)
    p = build_payslip(r, [], [], {}, ym="2026-06")
    by = {ln["label"]: ln for ln in p["lines"]}
    assert by["Lương chờ hàng"]["value"] == 300_000
    s = sum(ln["value"] for ln in p["lines"] if ln["kind"] == "money" and not ln["total"])
    assert s == by["THỰC NHẬN"]["value"]
    # không có khoản chờ hàng thì KHÔNG in dòng rỗng
    assert "Lương chờ hàng" not in _labels(build_payslip(_row(cho_hang=0), [], [], {}, ym="2026-06"))


def test_thanh_chuyen_tho_chi_hien_khi_co_tu_2_nguoi():
    """Thanh chuyển thợ: tên có link, người đang xem được đánh dấu, 1 thợ thì bỏ hẳn."""
    from renderers.phieu_luong_thang import _nav
    html = _nav({"workers": [{"id": 7, "name": "Trí", "current": True},
                             {"id": 9, "name": "Phượng", "current": False}]})
    assert 'data-w="7"' in html and 'class="nav-w on"' in html and "Phượng" in html
    assert "token" not in html          # token KHÔNG được nhúng vào HTML
    assert _nav({"workers": [{"id": 7, "name": "Trí", "current": True}]}) == ""
    assert _nav({}) == ""


def test_bang_cham_cong_o_0_de_trong():
    """Cột Giờ/TC: số 0 in ra Ô TRỐNG (không phải '0,0') — ngày nghỉ / không tăng ca
    để trống thì mắt bắt ngay ngày CÓ số."""
    from renderers.phieu_luong_thang import _hrs0, _day_row
    assert _hrs0(0) == "" and _hrs0(0.04) == "" and _hrs0(None) == ""
    assert _hrs0(7.95) == "8,0" and _hrs0(0.6) == "0,6"
    # ngày nghỉ: 4 ô giờ là ":" (thiếu mốc chấm) còn 2 ô số thì rỗng hẳn
    row = _day_row({"d": "02/07", "dow": "T.5", "slots": ["", "", "", ""], "gio": 0, "tc": 0})
    assert row.count('<td class="num"></td>') == 2
    assert "0,0" not in row


def test_slots_chia_theo_buoi_khong_ghep_tuan_tu():
    # chỉ làm buổi chiều → 2 ô SAU, 2 ô sáng để trống (nhìn là biết nghỉ buổi nào)
    assert _slots(["12:48", "17:33"]) == (["", "", "12:48", "17:33"], 0)
    assert _slots(["06:54", "11:04"]) == (["06:54", "11:04", "", ""], 0)
    assert _slots(["07:33"]) == (["07:33", "", "", ""], 0)
    # buổi có nhiều hơn 2 mốc: giữ đầu–cuối, đếm phần dôi để phiếu không giấu số liệu
    assert _slots(["07:00", "09:00", "11:00"]) == (["07:00", "11:00", "", ""], 1)
