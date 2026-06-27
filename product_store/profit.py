from __future__ import annotations
import json

from .queries import get_product


def calculate_order_profit(conn, order: dict) -> dict:
    invoice = order.get("invoice") or order.get("invoice_items") or []
    vat, pvc, discount = int(order.get("vat", 0)), int(order.get("pvc", 0)), int(order.get("discount", 0))
    fee_total = vat + pvc - discount
    items_profit, total_revenue, total_cost = [], 0, 0
    for item in invoice:
        code = (item.get("sp") or "").upper().strip()
        if not code:
            continue
        qty, sell_price = int(item.get("sl", 0)), int(item.get("price", 0))
        revenue = qty * sell_price
        frozen_cost = item.get("cost_price")
        if frozen_cost is not None:
            cost_price, is_frozen = int(frozen_cost), True
        else:
            product = get_product(conn, code)
            cost_price, is_frozen = (product.get("cost_price", 0) if product else 0), False
        cost = qty * cost_price
        profit = (revenue - cost) if cost_price > 0 else 0
        items_profit.append({"code": code, "qty": qty, "sell_price": sell_price, "cost_price": cost_price, "revenue": revenue, "cost": cost, "profit": profit, "has_cost": cost_price > 0, "is_frozen": is_frozen})
        total_revenue += revenue
        if cost_price > 0:
            total_cost += cost
    total_profit = sum(i["profit"] for i in items_profit) + fee_total if total_cost > 0 else 0
    return {"items": items_profit, "total_revenue": total_revenue + fee_total, "total_cost": total_cost, "total_profit": total_profit, "item_count": len(items_profit), "items_with_cost": sum(1 for i in items_profit if i["has_cost"]), "fees": {"vat": vat, "pvc": pvc, "discount": discount, "fee_total": fee_total}}


def freeze_invoice_cost_prices(conn, invoice: list) -> list:
    out = []
    for item in invoice:
        if "cost_price" not in item:
            code = (item.get("sp") or "").upper().strip()
            if code:
                product = get_product(conn, code)
                if product and product.get("cost_price", 0) > 0:
                    item = {**item, "cost_price": product["cost_price"]}
        out.append(item)
    return out


def get_products_from_orders(conn, limit: int = 200) -> list[str]:
    codes = set()
    for row in conn.execute("SELECT json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall():
        order = json.loads(row[0])
        for item in order.get("invoice") or order.get("invoice_items") or []:
            code = (item.get("sp") or "").upper().strip()
            if code:
                codes.add(code)
    return sorted(codes)
