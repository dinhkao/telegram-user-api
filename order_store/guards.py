"""Rule chặn thao tác task theo trạng thái đơn — dùng chung web API + lệnh Telegram.

Hiện có: soạn hàng chỉ đánh dấu xong được khi đơn ĐÃ CHỐT xuất kho và CÓ ảnh
soạn hàng (kind='soan_hang', chưa xoá mềm). Bật/tắt qua settings_store
['soan_hang_require_stock'] (mặc định BẬT). Nối: settings_store, bảng order_images.
"""
from __future__ import annotations


def soan_hang_block_reason(conn, thread_id: int, order: dict) -> str | None:
    """Lý do CHẶN đánh dấu 'soạn hàng' xong (None = cho phép)."""
    from settings_store import get_bool
    if not get_bool("soan_hang_require_stock", True):
        return None
    sc = order.get("stock_confirmed")
    if not (isinstance(sc, dict) and sc):
        return "Chưa chốt xuất kho — chốt xuất kho xong mới đánh dấu soạn hàng được"
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM order_images WHERE thread_id = ? AND kind = 'soan_hang' AND deleted_at IS NULL",
            (thread_id,),
        ).fetchone()[0]
    except Exception:   # bảng chưa có (DB mới) → coi như chưa có ảnh
        n = 0
    if not n:
        return "Chưa có ảnh soạn hàng — chụp ảnh soạn hàng rồi mới đánh dấu được"
    return None
