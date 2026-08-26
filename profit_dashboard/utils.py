"""Helpers thuần của dashboard lợi nhuận: tên khách của đơn + phân bổ tiền vay.

(Đống helper HTML/CSS/JS của bộ trang server-render cũ đã gỡ 2026-08-26 — UI giờ
là webapp #/loi-nhuan, xem profit_dashboard/compute.py.)
"""
from __future__ import annotations
import calendar
import json

from profit_dashboard.settings import DEFAULT_WEIGHTS


# Cache of customers.firebase_key -> name, keyed by id(db_conn).
# Names change rarely and legacy orders only reference existing customers,
# so a per-connection cache is safe for the long-lived aiohttp app.
_CUSTOMER_NAME_MAP_CACHE = {}


def _customer_name_map(db_conn):
    """Build/return {firebase_key(str): name} for all customers on this conn."""
    cache_key = id(db_conn)
    cached = _CUSTOMER_NAME_MAP_CACHE.get(cache_key)
    if cached is not None:
        return cached
    m = {}
    try:
        cur = db_conn.execute(
            "SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL"
        )
        for fk, j in cur.fetchall():
            try:
                name = (json.loads(j) or {}).get("name")
            except Exception:
                name = None
            if name:
                m[str(fk)] = str(name)
    except Exception:
        pass
    _CUSTOMER_NAME_MAP_CACHE[cache_key] = m
    return m


def resolve_customer_name(db_conn, order):
    """Display name for an order's customer.

    Prefers the order's own denormalized ``customer_name``/``khach_hang`` field;
    for older orders that never stored it, falls back to the customers table via
    ``khach_hang_id`` (which equals customers.firebase_key). Returns "" if unknown.
    """
    customer = order.get("customer_name") or order.get("khach_hang") or ""
    if isinstance(customer, dict):
        customer = customer.get("name", "")
    customer = str(customer or "").strip()
    if customer:
        return customer
    kh_id = order.get("khach_hang_id")
    if kh_id not in (None, ""):
        return _customer_name_map(db_conn).get(str(kh_id), "")
    return ""


def calc_prorated_loan(since_date, until_date, base_monthly_loan, weights=None):
    """Calculate loan allocation for a date range using monthly weights.

    Each month M gets: base_monthly_loan * weight[M] / avg_weight
    Prorated by actual overlap days within that month.
    """
    if base_monthly_loan <= 0:
        return 0
    if weights is None:
        weights = DEFAULT_WEIGHTS
    # Ensure all 12 months have a weight
    w = {str(m): float(weights.get(str(m), weights.get(m, 1.0))) for m in range(1, 13)}
    avg_weight = sum(w.values()) / 12.0
    if avg_weight <= 0:
        return 0

    total = 0.0
    current = since_date
    while current <= until_date:
        days_in_month = calendar.monthrange(current.year, current.month)[1]
        month_start = current.replace(day=1)
        month_end = current.replace(day=days_in_month)
        overlap_start = max(current, month_start)
        overlap_end = min(until_date, month_end)
        overlap_days = (overlap_end - overlap_start).days + 1
        monthly_amount = base_monthly_loan * w[str(current.month)] / avg_weight
        total += monthly_amount * overlap_days / days_in_month
        # advance to first day of next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)
    return int(total)
