"""Guard thuần cho API đơn: validate ngày giao (order_api_mutations.valid_ngay_giao —
chuỗi rác sort TRÊN mọi ngày trong _ngay_giao_due nên phải chặn lúc ghi) + guard
chống double-tap tạo đơn (order_api_create._dup_key/_mark_create)."""
from __future__ import annotations

from server_app import order_api_create as oc
from server_app.order_api_mutations import valid_ngay_giao


class ValidNgayGiaoTests:
    def test_date_only(self):
        assert valid_ngay_giao("2026-07-25")

    def test_date_time_t(self):
        assert valid_ngay_giao("2026-07-25T17:30")

    def test_date_time_space(self):
        assert valid_ngay_giao("2026-07-25 17:30")

    def test_rejects_junk_strings(self):
        # chuỗi rác đứng trên mọi ngày trong so-sánh-chuỗi → phải bị 400
        for bad in ("abc", "hom nay", "mai giao", "9999", "25/07/2026",
                    "2026-7-5", "2026-07-25T1730", "2026-07-25Txx:yy", ""):
            assert not valid_ngay_giao(bad), bad

    def test_rejects_impossible_dates(self):
        for bad in ("2026-13-01", "2026-02-30", "2026-00-10", "2026-07-32"):
            assert not valid_ngay_giao(bad), bad

    def test_rejects_impossible_times(self):
        for bad in ("2026-07-25T24:00", "2026-07-25T10:60", "2026-07-25 99:99"):
            assert not valid_ngay_giao(bad), bad

    def test_none_is_invalid_value(self):
        # handler xử lý None/'' = XOÁ ngày giao TRƯỚC khi gọi validate;
        # bản thân validator coi rỗng là không hợp lệ
        assert not valid_ngay_giao(None)


class CreateDupGuardTests:
    def setup_method(self):
        oc._recent_creates.clear()

    def test_key_normalizes_whitespace_and_case(self):
        assert oc._dup_key("duy", "  Khách A\n2 thùng  ") == oc._dup_key("duy", "khách a 2 thùng")

    def test_key_scoped_per_actor(self):
        assert oc._dup_key("a", "don x") != oc._dup_key("b", "don x")

    def test_blocks_repeat_within_ttl(self):
        k = oc._dup_key("duy", "don x")
        assert oc._mark_create(k, now=100.0)
        assert not oc._mark_create(k, now=100.1)          # double-tap
        assert not oc._mark_create(k, now=100.0 + oc._DUP_TTL - 0.01)

    def test_allows_after_ttl(self):
        k = oc._dup_key("duy", "don x")
        assert oc._mark_create(k, now=100.0)
        assert oc._mark_create(k, now=100.0 + oc._DUP_TTL)

    def test_failure_path_clears_key(self):
        k = oc._dup_key("duy", "don x")
        assert oc._mark_create(k, now=50.0)
        oc._recent_creates.pop(k, None)                   # đường tạo THẤT BẠI gỡ key
        assert oc._mark_create(k, now=50.5)

    def test_prunes_stale_entries(self):
        k1 = oc._dup_key("a", "don 1")
        k2 = oc._dup_key("b", "don 2")
        assert oc._mark_create(k1, now=10.0)
        assert oc._mark_create(k2, now=10.0 + oc._DUP_TTL + 5)
        assert k1 not in oc._recent_creates               # entry cũ được dọn

    def test_different_text_not_blocked(self):
        assert oc._mark_create(oc._dup_key("duy", "don x"), now=1.0)
        assert oc._mark_create(oc._dup_key("duy", "don y"), now=1.0)
