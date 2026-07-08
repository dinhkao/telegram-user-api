"""Rule ràng buộc QUY TRÌNH đơn — dùng chung web API + lệnh Telegram + print_service.

Chuỗi: chốt xuất kho + ảnh soạn hàng → soạn hàng → giao hàng → in HĐ giao.
Tất cả bật/tắt CHUNG 1 toggle settings_store['soan_hang_require_stock']
(mặc định BẬT, sửa ở trang Cài đặt webapp). Nối: settings_store, bảng order_images.
"""
from __future__ import annotations


def _rule_on() -> bool:
    from settings_store import get_bool
    return get_bool("soan_hang_require_stock", True)


def _step_done(order: dict, step: str) -> bool:
    """Bước coi như XONG khi done hoặc skip (bỏ qua chủ động) — khớp all_steps_done."""
    st = (order.get("task_status") or {}).get(step) or {}
    return bool(st.get("done") or st.get("skip"))


def soan_hang_block_reason(conn, thread_id: int, order: dict) -> str | None:
    """Lý do CHẶN đánh dấu 'soạn hàng' xong (None = cho phép)."""
    if not _rule_on():
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


def giao_hang_block_reason(order: dict) -> str | None:
    """Lý do CHẶN hoàn thành 'giao hàng' (None = cho phép): cần soạn hàng xong trước."""
    if not _rule_on():
        return None
    if not _step_done(order, "soan_hang"):
        return "Chưa xong soạn hàng — soạn hàng xong mới hoàn thành giao hàng được"
    return None


def print_giao_block_reason(order: dict) -> str | None:
    """Lý do CHẶN in hoá đơn giao (None = cho phép): cần giao hàng xong trước."""
    if not _rule_on():
        return None
    if not _step_done(order, "giao_hang"):
        return "Chưa hoàn thành giao hàng — giao xong mới in hoá đơn giao được"
    return None
