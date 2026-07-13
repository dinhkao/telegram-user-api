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
