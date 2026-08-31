"""Tính toán THUẦN cho dashboard lợi nhuận bản NATIVE trong webapp (#/loi-nhuan).

Trả dict JSON-ready cho server_app/profit_api_routes.py; chạy trong thread với
connection riêng (quét full bảng orders). Cùng luật với các trang HTML legacy đã
gỡ (2026-08-26): mốc thread_id ≥ MIN_THREAD_ID, ngày theo giờ VN, lợi nhuận từng
đơn = product_store.calculate_order_profit (giá vốn frozen ưu tiên). Kết nối:
order blob (orders), product_store, profit_dashboard.utils (loan proration).
Tests: tests/test_profit_compute.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from product_db import calculate_order_profit, get_all_products

from profit_dashboard.queries import MIN_THREAD_ID, _created_vn
from profit_dashboard.utils import calc_prorated_loan, resolve_customer_name


def scan_orders(conn, since: str | None, until: str | None) -> list[dict]:
    """1 lượt quét orders trong khoảng ngày (VN) → mỗi đơn 1 dict đã tính lãi."""
    cur = conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id >= ? ORDER BY thread_id DESC",
        (MIN_THREAD_ID,))
    out = []
    for row in cur.fetchall():
        order = json.loads(row[1])
        created = order.get("created", "")
        ymd, date_display = (None, "")
        if created:
            ymd, date_display = _created_vn(created)
            if ymd is None:
                continue
            if since and ymd < since:
                continue
            if until and ymd > until:
                continue
        res = calculate_order_profit(conn, order)
        if not res["items"]:
            continue
        out.append({
            "thread_id": row[0],
            "customer": str(resolve_customer_name(conn, order) or "") or "Khách lẻ",
            "has_payment": bool(order.get("payments")),
            "ymd": ymd,
            "date": date_display,
            "revenue": res["total_revenue"],
            "cost": res["total_cost"],
            "profit": res["total_profit"],
            "items": res["items"],
            "items_with_cost": res["items_with_cost"],
            "fees": res["fees"],
            "text": (order.get("text") or "").strip()[:80],
        })
    return out


def _pct(cur: float, prev: float) -> float | None:
    """% thay đổi so kỳ trước; None = kỳ trước bằng 0 (dữ liệu mới)."""
    if prev == 0:
        return None
    return round((cur - prev) / prev * 100, 1)


def _agg_customers(rows: list[dict]) -> dict[str, dict]:
    m: dict[str, dict] = {}
    for r in rows:
        c = m.setdefault(r["customer"], {"revenue": 0, "cost": 0, "profit": 0,
                                         "orders": 0, "products": set()})
        c["revenue"] += r["revenue"]
        c["cost"] += r["cost"]
        c["profit"] += r["profit"]
        c["orders"] += 1
        for it in r["items"]:
            c["products"].add(it["code"])
    return m


def _agg_products(rows: list[dict]) -> dict[str, dict]:
    m: dict[str, dict] = {}
    for r in rows:
        for it in r["items"]:
            p = m.setdefault(it["code"], {"qty": 0, "revenue": 0, "cost": 0, "profit": 0})
            p["qty"] += it["qty"]
            p["revenue"] += it["revenue"]
            p["cost"] += it["cost"]
            p["profit"] += it["profit"]
    return m


def _prev_range(since: str | None, until: str | None) -> tuple[str, str] | None:
    """Kỳ trước = cùng độ dài, lùi sát trước kỳ này."""
    try:
        start = datetime.strptime(since, "%Y-%m-%d").date()
        end = datetime.strptime(until, "%Y-%m-%d").date() if until else datetime.now().date()
        if end < start:
            end = start
        days = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)
        return prev_start.strftime("%Y-%m-%d"), prev_end.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _apply_filters(rows: list[dict], filter_product: str | None,
                   filter_customer: str | None) -> list[dict]:
    """Lọc theo mã SP (đơn có mã đó) + tên khách (chứa chuỗi, không phân biệt hoa
    thường) — cùng luật với bản legacy."""
    out = rows
    if filter_product:
        fp = filter_product.upper().strip()
        out = [r for r in out if any(it["code"] == fp for it in r["items"])]
    if filter_customer:
        fc = filter_customer.lower().strip()
        out = [r for r in out if fc in r["customer"].lower()]
    return out


def dashboard_data(conn, since: str | None, until: str | None,
                   yearly_loan: int, weights: dict | None,
                   filter_product: str | None = None,
                   filter_customer: str | None = None,
                   paid_only: bool = False) -> dict:
    all_rows = scan_orders(conn, since, until)
    # paid_only: CHỈ tính đơn ĐÃ có thanh toán (≥1 phiếu thu) — áp cho TẤT CẢ
    # (tóm tắt, bảng SP, chart, top 5, kỳ trước): đơn chưa thu không vào lợi nhuận
    if paid_only:
        all_rows = [r for r in all_rows if r["has_payment"]]
    # Filter áp vào summary/bảng SP/chart; TOP 5 vẫn tính trên dữ liệu KHÔNG lọc
    # (như bản gốc — top là "toàn cảnh kỳ này")
    rows = _apply_filters(all_rows, filter_product, filter_customer)
    revenue = sum(r["revenue"] for r in rows)
    cost = sum(r["cost"] for r in rows)
    profit = sum(r["profit"] for r in rows)

    # Kỳ trước (cùng độ dài, CÙNG bộ lọc) để so sánh %
    prev = {"revenue": 0, "cost": 0, "profit": 0, "orders": 0}
    prev_label = ""
    pr = _prev_range(since, until)
    if pr:
        prows = scan_orders(conn, pr[0], pr[1])
        if paid_only:
            prows = [r for r in prows if r["has_payment"]]
        prows = _apply_filters(prows, filter_product, filter_customer)
        prev = {"revenue": sum(r["revenue"] for r in prows),
                "cost": sum(r["cost"] for r in prows),
                "profit": sum(r["profit"] for r in prows), "orders": len(prows)}
        prev_label = f"{pr[0][8:10]}/{pr[0][5:7]} - {pr[1][8:10]}/{pr[1][5:7]}"

    # Top 5 khách / SP theo lãi (không lọc)
    cust_map = _agg_customers(all_rows)
    top_customers = [
        {"name": n, "revenue": d["revenue"], "profit": d["profit"], "orders": d["orders"]}
        for n, d in sorted(cust_map.items(), key=lambda x: x[1]["profit"], reverse=True)[:5]]
    top_map = _agg_products(all_rows)
    prod_map = _agg_products(rows)
    product_info = {p["code"]: p for p in get_all_products(conn)}
    top_products = [
        {"code": c, "qty": d["qty"], "revenue": d["revenue"], "profit": d["profit"]}
        for c, d in sorted(top_map.items(), key=lambda x: x[1]["profit"], reverse=True)[:5]]
    products = [{
        "code": c, "qty": d["qty"], "revenue": d["revenue"], "profit": d["profit"],
        "cost_price": int((product_info.get(c) or {}).get("cost_price") or 0),
        "name": (product_info.get(c) or {}).get("name") or "",
    } for c, d in sorted(prod_map.items(), key=lambda x: x[1]["profit"], reverse=True)[:150]]

    # Tiền vay phân bổ theo trọng số tháng + lãi thực
    base_monthly = (yearly_loan or 0) / 12.0
    loan = 0
    if base_monthly > 0 and since:
        try:
            start = datetime.strptime(since, "%Y-%m-%d").date()
            end = datetime.strptime(until, "%Y-%m-%d").date() if until else datetime.now().date()
            loan = calc_prorated_loan(start, end, base_monthly, weights)
        except (TypeError, ValueError):
            loan = int(base_monthly)
    real_profit = profit - loan
    margin = round(real_profit / revenue * 100, 1) if revenue > 0 else 0

    # Chuỗi theo NGÀY cho biểu đồ (60 ngày cuối của kỳ)
    daily: dict[str, dict] = {}
    for r in rows:
        if not r["ymd"]:
            continue
        d = daily.setdefault(r["ymd"], {"revenue": 0, "cost": 0, "profit": 0})
        d["revenue"] += r["revenue"]
        d["cost"] += r["cost"]
        d["profit"] += r["profit"]
    days = sorted(daily.keys())[-60:]
    chart = []
    for dstr in days:
        dl = 0
        if base_monthly > 0:
            try:
                dd = datetime.strptime(dstr, "%Y-%m-%d").date()
                dl = calc_prorated_loan(dd, dd, base_monthly, weights)
            except ValueError:
                dl = 0
        chart.append({"day": dstr, "revenue": daily[dstr]["revenue"],
                      "cost": daily[dstr]["cost"], "profit": daily[dstr]["profit"],
                      "real_profit": daily[dstr]["profit"] - dl})

    return {
        "summary": {
            "revenue": revenue, "cost": cost, "profit": profit, "orders": len(rows),
            "loan": loan, "real_profit": real_profit, "margin": margin,
            "changes": {"revenue": _pct(revenue, prev["revenue"]),
                        "cost": _pct(cost, prev["cost"]),
                        "profit": _pct(profit, prev["profit"]),
                        "orders": _pct(len(rows), prev["orders"])},
            "prev": prev, "prev_label": prev_label,
        },
        "top_customers": top_customers,
        "top_products": top_products,
        "products": products,
        "chart": chart,
    }


def customers_data(conn, since: str | None, until: str | None) -> dict:
    rows = scan_orders(conn, since, until)
    m = _agg_customers(rows)
    out = [{"name": n, "revenue": d["revenue"], "cost": d["cost"], "profit": d["profit"],
            "orders": d["orders"], "product_count": len(d["products"])}
           for n, d in sorted(m.items(), key=lambda x: x[1]["profit"], reverse=True)]
    return {"customers": out,
            "totals": {"revenue": sum(c["revenue"] for c in out),
                       "cost": sum(c["cost"] for c in out),
                       "profit": sum(c["profit"] for c in out),
                       "orders": sum(c["orders"] for c in out)}}


def customer_detail_data(conn, name: str, since: str | None, until: str | None) -> dict:
    rows = [r for r in scan_orders(conn, since, until)
            if r["customer"].lower() == (name or "").lower()]
    prod_map = _agg_products(rows)
    products = [{"code": c, "qty": d["qty"], "revenue": d["revenue"], "profit": d["profit"]}
                for c, d in sorted(prod_map.items(), key=lambda x: x[1]["profit"], reverse=True)]
    orders = [{k: r[k] for k in ("thread_id", "date", "revenue", "cost", "profit",
                                 "items", "items_with_cost", "text")} for r in rows]
    return {"name": name, "orders": orders, "products": products,
            "totals": {"revenue": sum(r["revenue"] for r in rows),
                       "cost": sum(r["cost"] for r in rows),
                       "profit": sum(r["profit"] for r in rows), "orders": len(rows)}}


def product_detail_data(conn, code: str, since: str | None, until: str | None) -> dict:
    code = (code or "").upper().strip()
    from product_db import get_product
    product = get_product(conn, code) or {"code": code, "name": "", "cost_price": 0}
    orders = []
    total = {"qty": 0.0, "revenue": 0, "cost": 0, "profit": 0}
    for r in scan_orders(conn, since, until):
        for it in r["items"]:
            if it["code"] != code:
                continue
            orders.append({"thread_id": r["thread_id"], "customer": r["customer"],
                           "date": r["date"], "ymd": r["ymd"], "qty": it["qty"],
                           "sell_price": it["sell_price"], "cost_price": it["cost_price"],
                           "revenue": it["revenue"], "cost": it["cost"],
                           "profit": it["profit"], "has_cost": it["has_cost"]})
            total["qty"] += it["qty"]
            total["revenue"] += it["revenue"]
            total["cost"] += it["cost"]
            total["profit"] += it["profit"]
    # Gộp cho khối "Báo cáo bán ra" ở trang chi tiết SP: top khách (theo doanh thu)
    # + chuỗi theo NGÀY cho biểu đồ
    cust: dict[str, dict] = {}
    daily: dict[str, dict] = {}
    for o in orders:
        c = cust.setdefault(o["customer"], {"qty": 0.0, "revenue": 0, "profit": 0, "orders": 0})
        c["qty"] += o["qty"]
        c["revenue"] += o["revenue"]
        c["profit"] += o["profit"]
        c["orders"] += 1
        if o["ymd"]:
            d = daily.setdefault(o["ymd"], {"qty": 0.0, "revenue": 0, "profit": 0})
            d["qty"] += o["qty"]
            d["revenue"] += o["revenue"]
            d["profit"] += o["profit"]
    top_customers = [{"name": n, **d} for n, d in
                     sorted(cust.items(), key=lambda x: x[1]["revenue"], reverse=True)]
    chart = [{"day": d, **daily[d]} for d in sorted(daily.keys())]
    total["customers"] = len(cust)
    return {"product": {"code": code, "name": product.get("name") or "",
                        "cost_price": int(product.get("cost_price") or 0)},
            "orders": orders, "totals": total,
            "top_customers": top_customers, "chart": chart}
