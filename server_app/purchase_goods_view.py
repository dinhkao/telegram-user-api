"""Gắn trạng thái NHẬP KHO vào row phiếu nhập cho API đọc — chỉ ĐỌC, không sửa DB.

Phiếu ĐÃ CHỐT: boxes theo snapshot goods_result (+ cờ box_deleted cho thùng đã
xoá hẳn). Phiếu ĐANG MỞ: gắn `draft_receipt` {new, existing, totals} derive live
(purchase_goods._draft_receipt) + boxes đang nhập → trang chi tiết vẽ tiến độ,
ô thùng (BoxLabelGrid), nút ✕ từng dòng và nút Chốt.
Dùng bởi: server_app/purchase_routes.py (GET chi tiết), purchase_goods_routes.py.
"""
from __future__ import annotations

from server_app.purchase_goods import _draft_receipt


def _attach_box_infos(conn, row: dict, ids: list[int]) -> None:
    from inventory_store.queries import get_box
    from inventory_store.allocations import list_box_allocations
    boxes, seen = [], set()
    for bid in ids:
        if not bid or bid in seen:
            continue
        seen.add(bid)
        b = get_box(conn, bid)
        if not b:
            continue
        b["remaining"] = float(b.get("quantity") or 0) - sum(
            float(a.get("quantity") or 0) for a in list_box_allocations(conn, bid))
        boxes.append(b)
    if boxes:
        row["boxes"] = boxes


def attach_purchase_boxes(conn, row: dict | None) -> dict | None:
    """Gắn row['boxes'] (info + remaining — BoxLabelGrid) và, với phiếu ĐANG MỞ,
    row['draft_receipt'] = trạng thái đang nhập {new, existing, totals}."""
    if not row:
        return row
    if row.get("goods_handled_at") and row.get("goods_result"):
        gr = row["goods_result"]
        ids = [e.get("box_id")
               for e in list(gr.get("restocked_new") or []) + list(gr.get("restocked_existing") or [])]
        _attach_box_infos(conn, row, ids)
        return row
    draft = _draft_receipt(conn, row["id"])
    if draft["new"] or draft["existing"]:
        # Gom theo danh tính SP (sp_id, fallback mã) — client khớp dòng phiếu qua
        # sp_id nên mã SP đổi tên giữa chừng không làm lệch tiến độ/prefill.
        totals: dict = {}
        for e in draft["new"] + draft["existing"]:
            k = e.get("sp_id") or e["sp"]
            cur = totals.setdefault(k, {"sp": e["sp"], "sp_id": e.get("sp_id"), "quantity": 0.0})
            cur["quantity"] += float(e["quantity"] or 0)
        row["draft_receipt"] = {
            "new": draft["new"], "existing": draft["existing"],
            "totals": list(totals.values()),
        }
        _attach_box_infos(conn, row, [e["box_id"] for e in draft["new"] + draft["existing"]])
    return row


def mark_deleted_boxes(conn, row: dict | None) -> dict | None:
    """Gắn box_deleted=True cho các entry goods_result mà thùng đã bị XOÁ HẲN
    khỏi kho (delete_box là hard-delete) — UI hiện 'đã xoá' thay vì link chết.
    goods_result là snapshot lịch sử nên chỉ đọc, không sửa DB."""
    gr = (row or {}).get("goods_result")
    if not row or not gr:
        return row
    entries = list(gr.get("restocked_existing") or []) + list(gr.get("restocked_new") or [])
    ids = [e.get("box_id") for e in entries if e.get("box_id")]
    if not ids:
        return row
    q = ",".join("?" for _ in ids)
    alive = {r[0] for r in conn.execute(
        f"SELECT id FROM inventory_boxes WHERE id IN ({q})", ids).fetchall()}
    for e in entries:   # e là reference vào dict trong row → gắn cờ tại chỗ
        if e.get("box_id") and e["box_id"] not in alive:
            e["box_deleted"] = True
    return row
