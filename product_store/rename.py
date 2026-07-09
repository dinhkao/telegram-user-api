"""Đổi MÃ sản phẩm theo DANH TÍNH (products.id bất biến) — mã chỉ là nhãn.

= UPDATE 1 ô code + ghi product_code_history (alias mã cũ) + refresh các cột mã
SNAPSHOT hiển thị (kho/công thức/SX — thuần cosmetic, mọi liên kết đã theo id
nên lệch cũng không sai logic). Bảng giá/đơn hàng KHÔNG cần đụng (key/sp_id theo
id, hiển thị resolve sống). Đẩy mã mới sang KiotViet làm best-effort ở route.
Nối: utils.db, .queries, .resolve, .schema (cache), order_store.display."""
from __future__ import annotations

import re
import sqlite3
import time

from utils.db import transaction

from .queries import get_product
from .resolve import record_code_change
from .schema import _invalidate_products_cache

_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")


def rename_product(conn, old_code, new_code, by: str = "") -> tuple[dict | None, str | None]:
    """Trả (product sau khi đổi, None) hoặc (None, lý do lỗi)."""
    old = str(old_code or "").strip().upper()
    new = str(new_code or "").strip().upper()
    if not old or not new:
        return None, "Thiếu mã"
    if new == old:
        return None, "Mã mới trùng mã cũ"
    if len(new) > 30:
        return None, "Mã quá dài (tối đa 30 ký tự)"
    if new.isdigit():
        return None, "Mã SP không được toàn chữ số"
    if not _CODE_RE.match(new):
        return None, "Mã chỉ gồm chữ/số và . _ - (bắt đầu bằng chữ/số)"
    prod = get_product(conn, old)
    if not prod:
        return None, f"Mã {old} không có trong danh mục"
    if get_product(conn, new):
        return None, f"Mã {new} đã tồn tại trong danh mục"
    pid = int(prod["id"])
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    try:
        with transaction(conn):
            conn.execute("UPDATE products SET code = ?, updated_at = ? WHERE id = ?", (new, now, pid))
            record_code_change(conn, pid, old, new, by)
            # refresh mã snapshot hiển thị nhanh (bảng có thể chưa tạo trên DB test)
            for sql in (
                "UPDATE inventory_boxes SET product_code = ? WHERE product_id = ?",
                "UPDATE product_recipes SET product_code = ? WHERE product_id = ?",
                "UPDATE product_recipes SET ingredient_code = ? WHERE ingredient_id = ?",
                "UPDATE production_slips SET sp_name = ? WHERE product_id = ?",
                "UPDATE production_report_rows SET product_code = ? WHERE product_id = ?",
            ):
                try:
                    conn.execute(sql, (new, pid))
                except sqlite3.OperationalError:
                    pass
    except sqlite3.Error as e:
        return None, f"Lỗi DB khi đổi mã: {e}"
    _invalidate_products_cache()
    try:
        from order_store.display import invalidate_display_maps
        invalidate_display_maps()
    except Exception:  # noqa: BLE001
        pass
    return get_product(conn, new), None
