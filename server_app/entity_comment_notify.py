"""PUSH khi có bình luận mới ở TRAO ĐỔI của thực thể ngoài đơn (thùng, phiếu SX, nhập
hàng, trả hàng, việc, vị trí, NCC, xuất huỷ, kho đậu, vệ sinh khu vực, chất lượng mâm,
trao đổi lương…). Đi qua server_app.notify.push_bg = cùng hàng đợi push bền với bình
luận đơn; thông báo mang `route` (hash webapp) → bấm mở đúng trang thực thể.

Trao đổi LƯƠNG (worker_*) → audience='office': chỉ văn phòng nhận push/thấy thông báo.
`describe` tra tên thực thể best-effort (lỗi/thiếu → nhãn chung). Nối: entity_media_routes
(gọi), app.db (tra tên), server_app.notify.
"""
from __future__ import annotations

import asyncio
import logging

from utils.db import get_connection

log = logging.getLogger("server")

# scope → (nhãn, mẫu route). {id} = entity_id; route None = tra thêm (xem describe).
_SCOPES: dict[str, tuple[str, str | None]] = {
    "box": ("Thùng", "#/thung/{id}"),
    "production": ("Phiếu SX", "#/san_xuat/{id}"),
    "purchase": ("Phiếu nhập", "#/nhap-hang/{id}"),
    "supplier": ("NCC", "#/ncc/{id}"),
    "return": ("Phiếu trả", "#/tra-hang/{id}"),
    "task": ("Việc", "#/viec/{id}"),
    "place": ("Vị trí", "#/vi-tri/{id}"),
    "disposal": ("Phiếu xuất huỷ", "#/xuat-huy/{id}"),
    "bean_slip": ("Phiếu kho đậu", "#/kho-dau/phieu/{id}"),
    "bean_stocktake": ("Kiểm kho đậu", "#/kho-dau/kiem/{id}"),
    "area_report": ("Vệ sinh", None), "area_image": ("Vệ sinh", None),
    "quality_report": ("Chất lượng mâm", None), "quality_image": ("Chất lượng mâm", None),
    "worker_moc": ("Mốc lương", "#/luong-thang/{id}"), "worker_pc": ("Phụ cấp", "#/luong-thang/{id}"),
    "worker_ung": ("Ứng lương", "#/luong-thang/{id}"), "worker_bhxh": ("BHXH", "#/luong-thang/{id}"),
}
OFFICE_SCOPES = {"worker_moc", "worker_pc", "worker_ung", "worker_bhxh"}


def _one(conn, sql: str, params) -> object:
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001 — bảng chưa có (DB lẻ/test)
        return None


def describe(conn, scope: str, eid: int) -> tuple[str, str]:
    """(tên hiển thị, route) của thực thể. Không bao giờ raise."""
    label, route = _SCOPES.get(scope, ("Trao đổi", None))
    name = ""
    if scope == "box":
        name = str(_one(conn, "SELECT box_code || ' · ' || COALESCE(product_code,'') FROM inventory_boxes WHERE id=?", (eid,)) or "")
    elif scope == "production":
        name = str(_one(conn, "SELECT s.sp_name FROM production_slips s WHERE s.thread_id=?", (eid,)) or "")
    elif scope == "purchase":
        name = str(_one(conn, "SELECT su.name FROM purchase_slips p LEFT JOIN suppliers su ON su.id=p.supplier_id WHERE p.id=?", (eid,)) or "")
    elif scope == "supplier":
        name = str(_one(conn, "SELECT name FROM suppliers WHERE id=?", (eid,)) or "")
    elif scope == "return":
        name = str(_one(conn, "SELECT json_extract(c.json,'$.name') FROM return_slips r LEFT JOIN customers c "
                              "ON c.firebase_key = r.customer_key WHERE r.id=?", (eid,)) or "")
    elif scope == "task":
        name = str(_one(conn, "SELECT title FROM web_tasks WHERE id=?", (eid,)) or "")
    elif scope == "place":
        name = str(_one(conn, "SELECT name FROM inventory_places WHERE id=?", (eid,)) or "")
    elif scope in OFFICE_SCOPES:
        name = str(_one(conn, "SELECT name FROM production_workers WHERE id=?", (eid,)) or "")
    elif scope in ("area_report", "area_image", "quality_report", "quality_image"):
        rid = eid
        if scope.endswith("_image"):   # entity_id = id ẢNH → báo cáo chứa ảnh
            rid = _one(conn, "SELECT entity_id FROM entity_images WHERE id=?", (eid,))
        if scope.startswith("area"):
            aid = _one(conn, "SELECT area_id FROM area_hygiene_reports WHERE id=?", (rid,))
            name = str(_one(conn, "SELECT name FROM workshop_areas WHERE id=?", (aid,)) or "")
            route = f"#/khu-vuc/{aid}" if aid else "#/khu-vuc"
        else:
            wid = _one(conn, "SELECT worker_id FROM tray_quality_reports WHERE id=?", (rid,))
            name = str(_one(conn, "SELECT name FROM production_workers WHERE id=?", (wid,)) or "")
            route = f"#/chat-luong/{wid}" if wid else "#/chat-luong"
    title = f"{label} #{eid}" if not name else f"{label} {name}" if scope in OFFICE_SCOPES or scope.startswith(("area", "quality")) else f"{label} #{eid} · {name}"
    if scope == "box":
        title = f"{label} {name}" if name else title
    return title.strip(), (route or "").format(id=eid)


async def notify_entity_comment(scope: str, entity_id: int, user: str, text: str, comment_id=None) -> None:
    """Ghi thông báo + push (hàng đợi bền) cho 1 bình luận thực thể. Không raise."""
    if scope not in _SCOPES:
        return
    try:
        def _d():
            conn = get_connection()
            try:
                return describe(conn, scope, int(entity_id))
            finally:
                conn.close()
        what, route = await asyncio.to_thread(_d)
        from server_app.notify import push_bg
        push_bg(f"💬 Trao đổi · {what}", f"{user}: {str(text or '')[:100]}",
                {"type": "comment", "scope": scope, "entity_id": str(entity_id),
                 "comment_id": str(comment_id or ""), "route": route},
                audience="office" if scope in OFFICE_SCOPES else None)
    except Exception as e:  # noqa: BLE001
        log.warning("notify entity comment %s/%s lỗi: %s", scope, entity_id, e)
