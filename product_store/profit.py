from __future__ import annotations
from utils.qty import parse_qty
import json

from .queries import get_product


def money_value(value) -> int:
    """Số tiền VND, chấp nhận trường tùy chọn null; từ chối NaN/Infinity."""
    from decimal import Decimal
    number = Decimal(str(value if value not in (None, "") else 0))
    if not number.is_finite():
        raise ValueError("Số tiền không hữu hạn")
    return int(round(number))


def product_identity(conn, item):
    """Chỉ resolve danh tính/mã; tuyệt đối không thay giá bán/vốn lịch sử."""
    from .queries import get_product_by_id
    from .resolve import resolve_code
    code = str(item.get("sp") or item.get("product_code") or "").upper().strip()
    product = None
    if conn is not None:
        try:
            product = get_product_by_id(conn, item.get("sp_id")) if item.get("sp_id") else None
        except (ValueError, TypeError):
            pass
        if product is None and code:
            product = resolve_code(conn, code)
    return (product or {}).get("code", code), (product or {}).get("id", item.get("sp_id"))


def calculate_order_profit(conn, order: dict) -> dict:
    """Doanh thu chưa VAT; lãi xác định chỉ dùng giá vốn đã lưu trong đơn.

    total_profit/known_profit là phần lãi đã xác định + phí/chiết khấu cấp đơn.
    complete_profit=None nếu thiếu vốn; dòng thiếu vốn có profit=None (không hòa vốn).
    Quy ước chủ hệ thống xác nhận 10/09/2026: cost_price đã tính sẵn VAT BÁN RA
    phải chịu. Vì thế lãi quản trị dùng tổng tiền khách trả GỒM VAT trừ vốn này.
    Không tự bóc 8% khỏi vốn, không cộng thêm chi phí VAT lần thứ hai.
    Doanh thu vẫn tách VAT; khoản VAT thu khách là điều chỉnh lãi ở cấp đơn.
    shipping_cost là chi phí giao hàng thực tế nếu có ghi.
    """
    invoice = order.get("invoice") or order.get("invoice_items") or []
    vat, pvc, discount = (money_value(order.get(k)) for k in ("vat", "pvc", "discount"))
    shipping_cost = money_value(order.get("shipping_cost"))
    revenue_fees = pvc - discount
    fee_total = vat + revenue_fees
    items_profit = []
    for item in invoice:
        if not isinstance(item, dict):
            raise ValueError("Dòng hóa đơn không hợp lệ")
        code, product_id = product_identity(conn, item)
        if not code:
            raise ValueError("Dòng hóa đơn thiếu mã sản phẩm")
        qty = parse_qty(item.get("sl") if item.get("sl") not in (None, "") else item.get("quantity", 0))
        sell_price = money_value(item.get("price"))
        revenue = round(qty * sell_price)
        frozen = item.get("cost_price")
        cost_price = money_value(frozen)
        # 0 cũ nghĩa là chưa nhập. 0 thật cần cờ xác nhận rõ ràng trong snapshot.
        has_cost = frozen is not None and (cost_price > 0 or
                   (cost_price == 0 and item.get("cost_confirmed") is True))
        has_cost = has_cost and item.get("cost_source") != "backfill_current"
        cost = round(qty * cost_price) if has_cost else 0
        items_profit.append({"code": code, "product_id": product_id,
            "original_code": str(item.get("sp") or ""), "qty": qty,
            "sell_price": sell_price, "cost_price": cost_price if has_cost else None,
            "revenue": revenue, "cost": cost,
            "profit": revenue - cost if has_cost else None,
            "has_cost": has_cost, "is_frozen": frozen is not None})
    goods = sum(i["revenue"] for i in items_profit)
    total_cost = sum(i["cost"] for i in items_profit)
    known_profit = sum(i["profit"] or 0 for i in items_profit) + fee_total - shipping_cost
    complete = all(i["has_cost"] for i in items_profit)
    return {"items": items_profit, "goods_revenue": goods,
        "total_revenue": goods + revenue_fees, "customer_total": goods + fee_total,
        "total_cost": total_cost, "total_profit": known_profit, "known_profit": known_profit,
        "complete_profit": known_profit if complete else None, "cost_complete": complete,
        "missing_cost_revenue": sum(i["revenue"] for i in items_profit if not i["has_cost"]),
        "item_count": len(items_profit), "items_with_cost": sum(i["has_cost"] for i in items_profit),
        "fees": {"vat": vat, "pvc": pvc, "discount": discount, "fee_total": fee_total,
                 "shipping_cost": shipping_cost},
        "cost_basis": "includes_output_vat_provision",
        "shipping_cost_recorded": order.get("shipping_cost") not in (None, "")}


def freeze_invoice_cost_prices(conn, invoice: list) -> list:
    """Choke point CHUNG cho mọi đường lưu invoice (web + Telegram). Mỗi dòng:
    - gắn `sp_id` = danh tính SP bất biến + CHUẨN HOÁ `sp` về mã hiện hành
      (gõ mã cũ vẫn nhận qua history — đổi mã SP không vỡ liên kết);
    - đông giá vốn 1 lần (cost_price) từ product_store;
    - gắn TÊN sản phẩm (snapshot) + cờ `known` (có trong danh mục?).
    known=False → mã lạ → UI cảnh báo. Giá là bản chụp lịch sử, KHÔNG resolve lại."""
    from .resolve import resolve_code
    out = []
    for item in invoice:
        code = (item.get("sp") or "").upper().strip()
        product = resolve_code(conn, code) if code else None
        item = {**item}
        if product:
            item["sp"] = product["code"]
            item["sp_id"] = product["id"]
        if "cost_price" not in item and product and product.get("cost_price", 0) > 0:
            item["cost_price"] = product["cost_price"]
        # Tên hiển thị: ưu tiên tên danh mục local, rồi tên KiotViet
        name = (product or {}).get("name") or (product or {}).get("kv_full_name")
        if name:
            item["name"] = name
        item["known"] = product is not None
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
