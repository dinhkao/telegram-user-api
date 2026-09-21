"""Bộ lọc dùng chung giữa tổng quan và feed, áp trên toàn đơn hàng."""
from __future__ import annotations

PAYMENT_FILTERS = {"all", "received", "unreceived"}
PROFIT_FILTERS = {"all", "positive", "loss", "breakeven", "low_margin"}
COST_FILTERS = {"all", "complete", "missing"}
ORDER_SORTS = {"newest", "oldest", "profit_desc", "profit_asc", "revenue_desc", "margin_asc"}


def apply_filters(rows, product=None, customer=None, *, paid_only=False,
                  payment="all", profitability="all", cost_status="all"):
    product = (product or "").strip().upper()
    customer = (customer or "").strip().casefold()
    out = []
    for row in rows:
        # Phiếu trả không phải đơn bán có trạng thái thu tiền/mức lãi.
        if row.get("kind") == "return" and (paid_only or payment != "all" or profitability != "all"):
            continue
        if product and not any(it["code"] == product for it in row["items"]):
            continue
        if customer and customer not in row["customer"].casefold():
            continue
        if (payment == "received" or (payment == "all" and paid_only)) and not row["has_payment"]:
            continue
        if payment == "unreceived" and row["has_payment"]:
            continue
        complete = all(it["has_cost"] for it in row["items"])
        if cost_status == "complete" and not complete:
            continue
        if cost_status == "missing" and complete:
            continue
        # Chưa đủ giá vốn thì không thể kết luận đơn lỗ, hoà vốn hay biên thấp.
        if profitability != "all":
            if not complete:
                continue
            profit, revenue = row["profit"], row["revenue"]
            if profitability == "positive" and profit <= 0:
                continue
            if profitability == "loss" and profit >= 0:
                continue
            if profitability == "breakeven" and profit != 0:
                continue
            if profitability == "low_margin" and not (revenue > 0 and 0 <= profit / revenue < .1):
                continue
        out.append(row)
    return out


def sort_orders(rows, sort="newest"):
    if sort in {"profit_desc", "profit_asc", "revenue_desc"}:
        key = "revenue" if sort == "revenue_desc" else "profit"
        return sorted(rows, key=lambda r: (r[key], r["thread_id"]), reverse=sort != "profit_asc")
    if sort == "margin_asc":
        return sorted(rows, key=lambda r: (
            r["profit"] / r["revenue"] if r["revenue"] > 0 and
            all(it["has_cost"] for it in r["items"]) else float("inf"), r["thread_id"]))
    return sorted(rows, key=lambda r: (r["ymd"] or "", r["thread_id"]), reverse=sort != "oldest")
