"""Unit test cho default_ngay_giao — mốc 17:30 giờ VN dời ngày giao sang hôm sau."""
from datetime import datetime, timedelta, timezone

from channel_handlers.config import default_ngay_giao

VN = timezone(timedelta(hours=7))


def test_before_cutoff_same_day():
    assert default_ngay_giao(datetime(2026, 7, 4, 9, 0, tzinfo=VN)) == "2026-07-04T00:00"


def test_just_before_cutoff_same_day():
    assert default_ngay_giao(datetime(2026, 7, 4, 17, 29, tzinfo=VN)) == "2026-07-04T00:00"


def test_at_cutoff_next_day():
    assert default_ngay_giao(datetime(2026, 7, 4, 17, 30, tzinfo=VN)) == "2026-07-05T00:00"


def test_after_cutoff_next_day():
    assert default_ngay_giao(datetime(2026, 7, 4, 20, 15, tzinfo=VN)) == "2026-07-05T00:00"


def test_month_rollover():
    assert default_ngay_giao(datetime(2026, 7, 31, 18, 0, tzinfo=VN)) == "2026-08-01T00:00"


def test_year_rollover():
    assert default_ngay_giao(datetime(2026, 12, 31, 23, 59, tzinfo=VN)) == "2027-01-01T00:00"
