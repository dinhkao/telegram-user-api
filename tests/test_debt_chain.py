"""Test chuỗi nợ feed khách + phân bổ loạt phiếu thu (bug nợ trùng khi thu liền tay).

Kịch bản thật (Chị Trang Cửa 3, 2026-07-08): 3 phiếu thu cách nhau 3s → resync
+6s của từng phiếu đều đọc cùng nợ CUỐI từ KiotViet → cả 3 bị ghi new_debt=0.
Nối: server_app/feed_debt._fill_debt_chain, server_app/debt_sync.derive_batch_new_debt.
"""
from server_app.feed_debt import _fill_debt_chain
from server_app.debt_sync import derive_batch_new_debt


def _pay(ts, amount, stored=None):
    return {"ts": ts, "kind": "payment", "delta": -float(amount), "stored": stored}


def _order(ts, total, stored=None):
    return {"ts": ts, "kind": "order", "delta": float(total), "stored": stored}


class DuplicateNewDebtGuardTests:
    def test_trang_cua_3_scenario_repaired(self):
        # mốc: phiếu thu cũ nợ về 0 → 3 đơn HĐ (800k+310k+170k) → 3 phiếu thu
        # liền tay ĐỀU bị ghi new_debt=0 (bug) → nợ hiện tại KV = 0
        events = [
            _pay(1, 340_000, stored=0.0),
            _order(2, 800_000), _order(3, 310_000), _order(4, 170_000),
            _pay(5, 800_000, stored=0.0),    # đúng phải là 480k
            _pay(6, 310_000, stored=0.0),    # đúng phải là 170k
            _pay(7, 170_000, stored=0.0),    # 0 — đúng
        ]
        _fill_debt_chain(events, current_debt=0.0)
        assert events[4]["debt_after"] == 480_000 and events[4]["est"]
        assert events[5]["debt_after"] == 170_000 and events[5]["est"]
        assert events[6]["debt_after"] == 0.0 and not events[6]["est"]

    def test_duplicate_with_invoice_between_is_kept(self):
        # nợ trùng NHƯNG có HĐ chen giữa đúng bằng amount → hợp lệ, không đụng
        events = [
            _pay(1, 100_000, stored=50_000.0),
            _order(2, 100_000),
            _pay(3, 100_000, stored=50_000.0),
        ]
        _fill_debt_chain(events, current_debt=50_000.0)
        assert not events[0]["est"] and events[0]["debt_after"] == 50_000
        assert not events[2]["est"] and events[2]["debt_after"] == 50_000

    def test_unbalanced_segment_stays_blank(self):
        # nợ trùng bị bỏ nhưng đoạn giữa 2 mốc KHÔNG CÂN (thiếu sự kiện ngoài app)
        # → giữ '—', không bịa số
        events = [
            _pay(1, 50_000, stored=900_000.0),    # mốc trước
            _pay(2, 100_000, stored=500_000.0),   # trùng với phiếu sau → bỏ
            _pay(3, 100_000, stored=500_000.0),   # mốc sau: 900k−200k=700k ≠ 500k → lệch
        ]
        _fill_debt_chain(events, current_debt=500_000.0)
        assert events[1]["debt_after"] is None


class MisplacedAnchorTests:
    """Mốc đúng-số-nhưng-SAI-CHỖ: HĐ KiotViet tạo TRỄ (sau phiếu thu kế đó) →
    khDebt snapshot chụp lúc nợ đã trả → mốc của đơn lệch khỏi dòng thời gian."""

    def test_vinh_bay_tinh_invoice_created_after_payment(self):
        # Kịch bản thật (Vinh Bảy Tình, 2026-07-13): đơn 12/07 780k (mốc 780k) →
        # đơn 13/07 1.170k nhưng HĐ KV tạo SAU phiếu thu → khDebt=0 → mốc 1.170k
        # sai chỗ; phiếu thu 780k mốc 1.170k (resync đọc sau khi HĐ vào). Trước
        # fix: rail đọc 780k → 1.170k → 1.170k (thu tiền nợ không giảm). Sau fix:
        # demote mốc đơn 13/07 → 780k → ≈1.950k → 1.170k.
        events = [
            _order(1, 780_000, stored=780_000.0),
            _order(2, 1_170_000, stored=1_170_000.0),   # khDebt=0 vì HĐ tạo sau thu
            _pay(3, 780_000, stored=1_170_000.0),
        ]
        _fill_debt_chain(events, current_debt=1_170_000.0)
        assert events[0]["debt_after"] == 780_000 and not events[0]["est"]
        assert events[1]["debt_after"] == 1_950_000 and events[1]["est"]
        assert events[2]["debt_after"] == 1_170_000 and not events[2]["est"]

    def test_unprovable_gap_keeps_all_anchors(self):
        # Lệch KHÔNG bắc cầu được (chỉnh nợ tay KiotViet chen giữa) → giữ nguyên
        # mọi mốc gốc như cũ, không demote bừa.
        events = [
            _order(1, 100_000, stored=100_000.0),
            _order(2, 100_000, stored=500_000.0),   # +300k chỉnh tay ngoài app
        ]
        _fill_debt_chain(events, current_debt=500_000.0)
        assert events[0]["debt_after"] == 100_000 and not events[0]["est"]
        assert events[1]["debt_after"] == 500_000 and not events[1]["est"]

    def test_demote_two_consecutive_misplaced_anchors(self):
        # 2 đơn liên tiếp đều có HĐ tạo trễ (khDebt cùng chụp sai thời điểm) →
        # bỏ cả 2 mốc mới cân: 500k → ≈1.000k → ≈1.500k → thu 1.500k về 0.
        events = [
            _pay(1, 500_000, stored=500_000.0),      # mốc tin được
            _order(2, 500_000, stored=2_000_000.0),  # mốc rác (sai chỗ)
            _order(3, 500_000, stored=2_000_000.0),  # mốc rác (sai chỗ)
            _pay(4, 1_500_000, stored=0.0),
        ]
        _fill_debt_chain(events, current_debt=0.0)
        assert events[1]["debt_after"] == 1_000_000 and events[1]["est"]
        assert events[2]["debt_after"] == 1_500_000 and events[2]["est"]
        assert events[3]["debt_after"] == 0.0 and not events[3]["est"]

    def test_anchor_next_to_virtual_current(self):
        # Mốc sai chỗ nằm SÁT mốc ảo "hiện tại" (không có mốc lưu nào sau nó)
        # vẫn demote được nhờ mốc ảo làm đầu phải của đoạn.
        events = [
            _order(1, 300_000, stored=300_000.0),
            _order(2, 200_000, stored=200_000.0),   # khDebt=0 sai chỗ (đúng: 500k)
        ]
        _fill_debt_chain(events, current_debt=500_000.0)
        assert events[0]["debt_after"] == 300_000 and not events[0]["est"]
        assert events[1]["debt_after"] == 500_000 and events[1]["est"]

    def test_mutually_balancing_misplaced_anchors_escalation(self):
        # Review 2026-07-13: 2 HĐ nhập trễ CÙNG ĐỢT → khDebt chụp liên tiếp →
        # 2 mốc rác TỰ CÂN với nhau (cặp 'tốt' giả chẻ đoạn lệch) → bắc cầu cục
        # bộ thất bại. Leo thang nới đoạn phải tìm ra cầu 500k → nợ hiện 1.000k.
        events = [
            _order(1, 500_000, stored=500_000.0),      # mốc đúng
            _order(2, 500_000, stored=500_000.0),      # rác: khDebt=0 (HĐ trễ)
            _order(3, 500_000, stored=1_000_000.0),    # rác: khDebt=500k (HĐ trễ, cân với mốc trên)
            _pay(4, 500_000, stored=0.0),              # rác (resync chụp sớm)
        ]
        _fill_debt_chain(events, current_debt=1_000_000.0)
        assert events[0]["debt_after"] == 500_000 and not events[0]["est"]
        assert events[1]["debt_after"] == 1_000_000 and events[1]["est"]
        assert events[2]["debt_after"] == 1_500_000 and events[2]["est"]
        assert events[3]["debt_after"] == 1_000_000 and events[3]["est"]

    def test_guessed_ts_delta_never_evidence_for_demote(self):
        # Payment di sản (không created_at) neo cạnh đơn = vị trí ĐOÁN → không
        # được dùng delta đó làm bằng chứng demote mốc KiotViet thật.
        events = [
            _order(1, 500_000, stored=500_000.0),
            {**_pay(2, 800_000), "ts_guessed": True},   # thu gộp cũ, vị trí đoán
            _order(3, 300_000, stored=800_000.0),       # mốc THẬT — phải giữ nguyên
        ]
        _fill_debt_chain(events, current_debt=0.0)
        assert events[0]["debt_after"] == 500_000 and not events[0]["est"]
        assert events[2]["debt_after"] == 800_000 and not events[2]["est"]

    def test_bridge_yielding_negative_debt_rejected(self):
        # Cầu cân về mặt số nhưng nội suy lòi nợ ÂM giữa đoạn → trùng hợp,
        # không demote (giữ mốc gốc).
        events = [
            _order(1, 100_000, stored=100_000.0),
            _pay(2, 500_000),                           # −400k nếu nội suy → âm
            _order(3, 400_000, stored=999_000.0),       # mốc lệch nhưng phải GIỮ
        ]
        _fill_debt_chain(events, current_debt=0.0)
        assert events[2]["debt_after"] == 999_000 and not events[2]["est"]


class ReorderSwappedInvoicePaymentTests:
    """HĐ KiotViet đẩy lên SAU khi tạo topic đơn, rơi sau 1 phiếu thu KV đã áp
    trước → sort timestamp xếp [đơn, thu] nhưng nợ thật áp [thu, đơn]. Hoán vị lại
    theo mốc KiotViet để hiện SỐ THẬT thay vì demote vứt mốc rồi nội suy sai."""

    def test_loan_long_dai_invoice_pushed_after_applied_payment(self):
        # Ca thật (Loan Long Đại, 2026-07-06): đơn #491500 (HĐ tạo 15:00, khDebt=
        # 57.9tr → mốc 61tr) đứng TRƯỚC phiếu thu 10.115tr (15:05, new_debt=57.9tr)
        # theo timestamp, nhưng KiotViet áp phiếu thu TRƯỚC. Trước fix: demote vứt
        # cả 2 mốc → đơn ≈71.115tr, thu ≈61tr (SAI). Sau fix: hoán vị → cả 4 mốc
        # thật, không est.
        events = [
            _order(1, 975_000, stored=68_015_000.0),     # đơn trước (mốc)
            _order(2, 3_100_000, stored=61_000_000.0),    # HĐ đẩy lên KV sau phiếu thu
            _pay(3, 10_115_000, stored=57_900_000.0),     # KiotViet áp TRƯỚC đơn trên
            _order(4, 750_000, stored=61_750_000.0),      # đơn sau (mốc)
        ]
        _fill_debt_chain(events, current_debt=61_750_000.0)
        # đã hoán vị: phiếu thu lên trước HĐ #491500, mọi mốc là SỐ THẬT
        assert events[0]["debt_after"] == 68_015_000 and not events[0]["est"]
        assert events[1]["kind"] == "payment"
        assert events[1]["debt_after"] == 57_900_000 and not events[1]["est"]
        assert events[2]["kind"] == "order"
        assert events[2]["debt_after"] == 61_000_000 and not events[2]["est"]
        assert events[3]["debt_after"] == 61_750_000 and not events[3]["est"]

    def test_swap_not_applied_when_chain_already_consistent(self):
        # Cặp order→payment ĐÃ khớp thứ tự (cur_ok) → tuyệt đối không hoán vị.
        events = [
            _order(1, 0, stored=1_000_000.0),
            _order(2, 500_000, stored=1_500_000.0),
            _pay(3, 300_000, stored=1_200_000.0),
        ]
        _fill_debt_chain(events, current_debt=1_200_000.0)
        assert events[1]["kind"] == "order" and events[1]["debt_after"] == 1_500_000
        assert events[2]["kind"] == "payment" and events[2]["debt_after"] == 1_200_000

    def test_swap_skipped_when_payment_ts_guessed(self):
        # Phiếu thu di sản vị trí ĐOÁN (ts_guessed) → cấm dùng làm bằng chứng hoán
        # vị (giống guard demote) → thứ tự giữ nguyên.
        events = [
            _order(1, 975_000, stored=68_015_000.0),
            _order(2, 3_100_000, stored=61_000_000.0),
            {**_pay(3, 10_115_000, stored=57_900_000.0), "ts_guessed": True},
            _order(4, 750_000, stored=61_750_000.0),
        ]
        _fill_debt_chain(events, current_debt=61_750_000.0)
        assert events[1]["kind"] == "order"      # KHÔNG hoán vị
        assert events[2]["kind"] == "payment"

    def test_swap_skipped_without_preceding_anchor(self):
        # Cặp order→payment ở ĐẦU chuỗi (không có mốc trái để chứng minh) → no-op.
        events = [
            _order(1, 3_100_000, stored=61_000_000.0),
            _pay(2, 10_115_000, stored=57_900_000.0),
            _order(3, 750_000, stored=61_750_000.0),
        ]
        _fill_debt_chain(events, current_debt=61_750_000.0)
        assert events[0]["kind"] == "order"      # KHÔNG hoán vị
        assert events[1]["kind"] == "payment"


class DeriveBatchNewDebtTests:
    def test_distributes_backwards_from_kv(self):
        assert derive_batch_new_debt([800_000, 310_000, 170_000], 0) == [480_000, 170_000, 0]

    def test_single_payment_gets_kv_debt(self):
        assert derive_batch_new_debt([340_000], 120_000) == [120_000]

    def test_negative_means_invoice_interleaved(self):
        # phân bổ lòi số âm = có HĐ chen giữa loạt → None (caller chỉ vá phiếu cuối)
        assert derive_batch_new_debt([100_000], -200_000) is None

    def test_old_debt_crosscheck_passes_when_consistent(self):
        # old_debt cascade khớp (kịch bản trang cửa 3) → phân bổ bình thường
        assert derive_batch_new_debt(
            [800_000, 310_000, 170_000], 0,
            old_debts=[1_280_000, 480_000, 170_000]) == [480_000, 170_000, 0]

    def test_old_debt_crosscheck_catches_positive_interleave(self):
        # thu A (500k→400k) → xuất HĐ B +200k (→600k) → thu B 100k (→500k):
        # phân bổ ngược cho phiếu A ra 600k (dương, âm-check không bắt) nhưng
        # old_debt A = 500k → 500k−100k=400k ≠ 600k → None (không ghi số sai)
        assert derive_batch_new_debt(
            [100_000, 100_000], 500_000,
            old_debts=[500_000, 600_000]) is None

    def test_old_debt_none_skips_check(self):
        # phiếu cũ không có old_debt → không kiểm được → vẫn phân bổ (như trước)
        assert derive_batch_new_debt(
            [800_000, 170_000], 0, old_debts=[None, None]) == [170_000, 0]

    def test_last_payment_exempt_from_crosscheck(self):
        # phiếu CUỐI neo số KV — old_debt cuối lệch (stale) không chặn phân bổ
        assert derive_batch_new_debt(
            [100_000], 700_000, old_debts=[123_000]) == [700_000]
