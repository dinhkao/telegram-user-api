"""Ghi audit BIẾN ĐỘNG KHO → lịch sử THÙNG (scope 'box') + lịch sử VỊ TRÍ (scope
'place'). Mỗi biến động (nhập / chuyển kho / xuất-thu đơn / xoá / chuyển hàng) ghi
1 event gắn box_id VÀ place_id để 2 trang lịch sử đều thấy.

Handler thu thập snapshot trong `_run` (có conn) rồi gọi các log_* ở context async.
Đọc lại + gắn nhãn: server_app/entity_history (_INV_ACTIONS). Realtime: History
widget tự tải lại khi entity đổi.
"""
from __future__ import annotations

from audit_log import async_log_event
from server_app.tasks import spawn_tracked


def box_snapshot(conn, box_id) -> dict | None:
    """Ảnh chụp 1 thùng cho audit: id, vị trí, mã thùng/SP, số cây + còn lại."""
    from inventory_store import get_box, list_box_allocations
    b = get_box(conn, box_id)
    if not b:
        return None
    used = sum((a.get("quantity") or 0) for a in list_box_allocations(conn, box_id))
    return {
        "box_id": b.get("id"), "place_id": b.get("place_id"), "place_name": b.get("place_name"),
        "box_code": b.get("box_code"), "product_code": b.get("product_code"),
        "unit": b.get("product_unit") or "cây",
        "quantity": b.get("quantity"), "remaining": float(b.get("quantity") or 0) - used,
    }


def _emit(action: str, scope: str, thread_id, actor, actor_type: str, payload: dict) -> None:
    if not thread_id:
        return
    spawn_tracked("audit.inv", async_log_event(
        action, scope=scope, thread_id=int(thread_id), actor_type=actor_type,
        actor_id=actor, source="inventory", payload=payload))


def _box_and_place(action: str, snap: dict, actor, actor_type: str, extra: dict | None = None) -> None:
    """Ghi CÙNG 1 event cho cả thùng lẫn vị trí chứa nó."""
    pl = {"box_id": snap.get("box_id"), "box_code": snap.get("box_code"),
          "product_code": snap.get("product_code"), "quantity": snap.get("quantity"),
          "remaining": snap.get("remaining"), **(extra or {})}
    _emit(action, "box", snap.get("box_id"), actor, actor_type, pl)
    _emit(action, "place", snap.get("place_id"), actor, actor_type, pl)


def log_boxes_created(snaps: list[dict], *, actor, actor_type: str) -> None:
    for s in snaps:
        _box_and_place("box.created", s, actor, actor_type)


def log_boxes_allocated(items: list[dict], *, actor, actor_type: str) -> None:
    """items = snapshot + {order_thread_id, order_text, taken}."""
    for s in items:
        _box_and_place("box.allocated", s, actor, actor_type, extra={
            "order_thread_id": s.get("order_thread_id"), "order_text": s.get("order_text"),
            "taken": s.get("taken")})
    _log_order_stock("order.stock_allocated", items, actor, actor_type)


def log_boxes_released(items: list[dict], *, actor, actor_type: str) -> None:
    for s in items:
        _box_and_place("box.released", s, actor, actor_type, extra={
            "order_thread_id": s.get("order_thread_id"), "order_text": s.get("order_text"),
            "taken": s.get("taken")})
    _log_order_stock("order.stock_released", items, actor, actor_type)


def _log_order_stock(action: str, items: list[dict], actor, actor_type: str) -> None:
    """Gộp các thùng của cùng một thao tác vào lịch sử của chính đơn hàng."""
    grouped: dict[int, list[dict]] = {}
    for s in items:
        try:
            tid = int(s.get("order_thread_id"))
        except (TypeError, ValueError):
            continue
        grouped.setdefault(tid, []).append({
            "box_id": s.get("box_id"), "box_code": s.get("box_code"),
            "product_code": s.get("product_code"), "taken": s.get("taken"),
            # cho lịch sử đọc được "lấy 5 cây ... (thùng còn 15)" không phải tra lại
            "remaining": s.get("remaining"), "unit": s.get("unit"),
        })
    for tid, boxes in grouped.items():
        _emit(action, "order", tid, actor, actor_type, {"boxes": boxes})


def log_boxes_consumed(snaps: list[dict], *, target_code, slip_id, actor, actor_type: str) -> None:
    """NL bị TIÊU HAO để ĐÓNG GÓI sp khác (allocate_picks kind='production'). Ghi lịch
    sử thùng NL + vị trí NL. slip_id = phiếu SX đóng gói, target_code = SP thành phẩm."""
    for s in snaps:
        _box_and_place("box.consumed", s, actor, actor_type, extra={
            "taken": s.get("consumed_amount"), "target_code": target_code, "slip_id": slip_id})


def log_boxes_disposed(items: list[dict], *, disposal_id, reason, actor, actor_type: str) -> None:
    """Xuất hủy: ghi giảm tồn vào timeline thùng + vị trí, link về phiếu hủy."""
    for s in items:
        _box_and_place("box.disposed", s, actor, actor_type, extra={
            "taken": s.get("taken"), "disposal_id": disposal_id,
            "disposal_reason": str(reason or "").strip(),
        })


def log_boxes_disposal_released(items: list[dict], *, disposal_id, reason, actor, actor_type: str) -> None:
    """Xóa phiếu hủy: ghi lượng hàng được hoàn lại vào các timeline liên quan."""
    for s in items:
        _box_and_place("box.disposal_released", s, actor, actor_type, extra={
            "taken": s.get("taken"), "disposal_id": disposal_id,
            "disposal_reason": str(reason or "").strip(),
        })


def log_box_moved(snap: dict, *, from_place_id, from_name, to_place_id, to_name, actor, actor_type: str) -> None:
    """Chuyển kho: ghi vị trí lịch sử cho CẢ kho cũ (thùng rời) + kho mới (thùng đến).
    Lịch sử THÙNG đã có event 'Chuyển kho' từ middleware (POST /box/{id})."""
    base = {"box_id": snap.get("box_id"), "box_code": snap.get("box_code"),
            "product_code": snap.get("product_code"), "quantity": snap.get("quantity"),
            "remaining": snap.get("remaining"), "from_place_id": from_place_id, "from_name": from_name,
            "to_place_id": to_place_id, "to_name": to_name}
    # Lịch sử THÙNG: 1 event box.moved ghi rõ TỪ kho nào → ĐẾN kho nào (middleware chỉ
    # thấy place mới nên bị bỏ ở entity_history, event này thay thế).
    _emit("box.moved", "box", snap.get("box_id"), actor, actor_type, base)
    _emit("box.moved_out", "place", from_place_id, actor, actor_type, base)
    _emit("box.moved_in", "place", to_place_id, actor, actor_type, base)


def log_box_deleted(snap: dict, *, actor, actor_type: str) -> None:
    """Xoá thùng: ghi vào lịch sử VỊ TRÍ (thùng biến mất khỏi kho). Lịch sử thùng
    đã có event 'Xoá' từ middleware (DELETE /box/{id})."""
    _emit("box.deleted", "place", snap.get("place_id"), actor, actor_type,
          {"box_id": snap.get("box_id"), "box_code": snap.get("box_code"),
           "product_code": snap.get("product_code"), "quantity": snap.get("quantity")})


def log_transfer_places(from_snap: dict, to_snap: dict, quantity, *, actor, actor_type: str) -> None:
    """Chuyển hàng giữa 2 thùng: ghi lịch sử cho CẢ vị trí LẪN thùng 2 bên."""
    pc = from_snap.get("product_code")
    out_pl = {"box_id": from_snap.get("box_id"), "box_code": from_snap.get("box_code"),
              "product_code": pc, "quantity": quantity, "remaining": from_snap.get("remaining"),
              "to_box": to_snap.get("box_code"), "to_name": to_snap.get("place_name")}   # kho thùng ĐÍCH
    in_pl = {"box_id": to_snap.get("box_id"), "box_code": to_snap.get("box_code"),
             "product_code": pc, "quantity": quantity, "remaining": to_snap.get("remaining"),
             "from_box": from_snap.get("box_code"), "from_name": from_snap.get("place_name")}   # kho thùng NGUỒN
    _emit("box.transfer_out", "place", from_snap.get("place_id"), actor, actor_type, out_pl)
    _emit("box.transfer_in", "place", to_snap.get("place_id"), actor, actor_type, in_pl)
    # lịch sử THÙNG (box scope) — để box detail + timeline thùng thấy chuyển hàng
    _emit("box.transfer_out", "box", from_snap.get("box_id"), actor, actor_type, out_pl)
    _emit("box.transfer_in", "box", to_snap.get("box_id"), actor, actor_type, in_pl)
