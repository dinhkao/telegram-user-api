"""Tồn NGUYÊN LIỆU của các mã SP trong 1 đơn — cho khối "Xuất kho cho đơn".

Chỉ SP **đóng gói được** (`products.can_package`) và **đã khai công thức** mới có
dòng nguyên liệu: hết thùng thành phẩm thì còn đóng gói tiếp được hay không phụ
thuộc tồn NL. Chỉ lấy NL CHÍNH (aux=0) — NL phụ (bao bì/tem) không nói lên điều đó.

Nối: product_store (resolve mã hiện hành + cờ can_package), recipe_store
(list_recipe), inventory_routes._aux_available (tồn 1 mã, cùng công thức FIFO).
"""
from __future__ import annotations


def order_material_stock(conn, codes) -> dict:
    """{MÃ SP trong hoá đơn: [{code, ratio, stock, unit}]} — mã SP không đóng gói
    được / chưa có công thức thì KHÔNG có khoá trong dict."""
    # import trong hàm: inventory_routes import ngược module này (vòng ở import-time)
    from server_app.inventory_routes import _aux_available
    from product_store import resolve_code
    from recipe_store import list_recipe

    out: dict = {}
    cache: dict = {}     # mã NL → (tồn, đơn vị) — nhiều SP thường chung 1 NL
    for c in codes:
        prod = resolve_code(conn, c)
        if not prod or not prod.get("can_package"):
            continue
        lines = list_recipe(conn, prod["code"], aux=False)
        if not lines:
            continue
        mats = []
        for ln in lines:
            ic = ln["ingredient_code"]
            if ic not in cache:
                ing = resolve_code(conn, ic)
                cache[ic] = (round(_aux_available(conn, ic, None), 3),
                             (ing.get("unit") if ing else None) or "cây")
            stock, unit = cache[ic]
            mats.append({"code": ic, "ratio": float(ln["ratio"] or 0),
                         "stock": stock, "unit": unit})
        if mats:
            out[c] = mats
    return out
