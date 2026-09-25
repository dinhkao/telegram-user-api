"""SỬA phần XỬ LÝ HÀNG của phiếu trả (sau khi đã nhập kho / xuất hủy) — thuần store,
không HTTP (routes: server_app/return_goods_edit_routes.py; tests: tests/test_return_goods.py).

Mô hình: `goods_result` của phiếu (return_store) là danh sách các dòng ĐÃ xử lý;
phần CHƯA xử lý = hàng trên phiếu − đã xử lý, tính theo danh tính SP (products.id,
fallback mã — purchase_goods._product_key). Nên:
  • GỠ 1 dòng (revert_goods_line) chỉ khi hàng đó CHƯA đi đâu:
      restocked_new      → thùng mới CHƯA có allocation nào (chưa xuất/chuyển/điều chỉnh) → xoá thùng
      restocked_existing → thùng còn ≥ phần đã cộng → xoá allocation return_in đó
      disposed           → rút khỏi phiếu hủy box-less (không đụng tồn); phiếu hủy rỗng → xoá mềm
    Gỡ hết mọi dòng → phiếu về CHƯA xử lý (goods_handled_at = NULL, xoá được).
  • Phần gỡ ra thành "chưa xử lý" → xử lý tiếp qua return_goods.apply_goods_dispositions.
  • Sửa hàng trên phiếu (mã/SL/đơn giá) được phép khi đã xử lý hàng, miễn SL từng SP
    không thấp hơn phần đã xử lý (check_items_cover_handled) — đổi đơn giá luôn được.
Nối: inventory_store (get_box/delete_box/list_box_allocations), disposal_store (bảng
disposal_slips), return_store, server_app.inventory_audit (snapshot cho event kho).
"""
from __future__ import annotations

import json as _json
from datetime import datetime as _dt, timezone as _tz, timedelta as _td

from utils.qty import fmt_qty, parse_qty

_KINDS = ("restocked_new", "restocked_existing", "disposed")
_EPS = 1e-9


def _key(conn, code, product_id=None):
    from server_app.purchase_goods import _product_key
    return _product_key(conn, code, product_id)


def _line_code(kind: str, line: dict) -> str:
    return str(line.get("product_code") if kind == "disposed" else line.get("sp") or "").strip().upper()


def handled_by_key(conn, goods_result) -> dict:
    """{khoá SP: tổng đã xử lý} từ goods_result (nhập thùng có sẵn + thùng mới + hủy)."""
    out: dict = {}
    for kind in _KINDS:
        for line in (goods_result or {}).get(kind) or []:
            k, _ = _key(conn, _line_code(kind, line))
            out[k] = out.get(k, 0.0) + parse_qty(line.get("quantity"))
    return out


def goods_pending(conn, r: dict) -> list[dict]:
    """Hàng CHƯA xử lý của phiếu: [{sp (mã hiện hành), quantity}] theo thứ tự dòng phiếu."""
    handled = handled_by_key(conn, r.get("goods_result"))
    want: dict = {}
    order: list = []
    for it in r.get("items") or []:
        k, live = _key(conn, it.get("sp"), it.get("sp_id"))
        if k not in want:
            order.append((k, live or str(it.get("sp") or "").upper()))
        want[k] = want.get(k, 0.0) + parse_qty(it.get("sl"))
    out = []
    for k, code in order:
        left = round(want[k] - handled.get(k, 0.0), 6)
        if left > _EPS:
            out.append({"sp": code, "quantity": left})
    return out


def with_pending(conn, row: dict | None) -> dict | None:
    """Gắn `goods_pending` vào dict phiếu trả để webapp hiện/prefill 'Xử lý tiếp'."""
    if row:
        row = {**row, "goods_pending": goods_pending(conn, row) if not row.get("deleted_at") else []}
    return row


def check_items_cover_handled(conn, r: dict, new_items: list[dict]) -> str | None:
    """Sửa hàng trên phiếu đã xử lý: SL mới của từng SP phải ≥ phần đã xử lý của SP đó
    (không thì kho có hàng mà phiếu không còn dòng). None = hợp lệ, str = lỗi VN."""
    handled = handled_by_key(conn, r.get("goods_result"))
    if not handled:
        return None
    new: dict = {}
    for it in new_items:
        k, _ = _key(conn, it.get("sp"), it.get("sp_id"))
        new[k] = new.get(k, 0.0) + parse_qty(it.get("sl"))
    for k, q in handled.items():
        if new.get(k, 0.0) + _EPS < q:
            label = k[1] if k[0] == "code" else _code_of(conn, k[1])
            return (f"{label} đã xử lý {fmt_qty(q)} (nhập kho/hủy) — SL trên phiếu không được nhỏ hơn. "
                    f"Gỡ dòng xử lý hàng của mã này trước rồi mới giảm/đổi mã.")
    return None


def _code_of(conn, product_id: int) -> str:
    row = conn.execute("SELECT code FROM products WHERE id = ?", (product_id,)).fetchone()
    return str(row[0]) if row else f"SP #{product_id}"


def _now_vn() -> str:
    return _dt.now(_tz(_td(hours=7))).isoformat(timespec="seconds")


class _Err(Exception):
    pass


def _revert_new_box(conn, return_id: int, line: dict) -> dict:
    from inventory_store import get_box, list_box_allocations
    from inventory_store.queries import delete_box
    from server_app.inventory_audit import box_snapshot
    box_id = int(line.get("box_id") or 0)
    box = get_box(conn, box_id)
    if not box or int(box.get("source_return_id") or 0) != return_id:
        raise _Err(f"Không tìm thấy thùng {line.get('box_code')} của phiếu trả này")
    if list_box_allocations(conn, box_id):
        raise _Err(f"Thùng {box.get('box_code')} đã xuất/chuyển/điều chỉnh — không gỡ được")
    snap = box_snapshot(conn, box_id)
    delete_box(conn, box_id)
    return {"deleted": [snap] if snap else []}


def _revert_existing(conn, return_id: int, line: dict) -> dict:
    from server_app.inventory_audit import box_snapshot
    box_id = int(line.get("box_id") or 0)
    q = parse_qty(line.get("quantity"))
    row = conn.execute(
        "SELECT id FROM box_allocations WHERE box_id = ? AND order_thread_id = ? AND kind = 'return_in'"
        " AND ABS(quantity + ?) < 1e-6 ORDER BY id DESC LIMIT 1", (box_id, return_id, q)).fetchone()
    if not row:
        raise _Err(f"Không tìm thấy phần hàng trả đã cộng vào thùng {line.get('box_code')}")
    snap = box_snapshot(conn, box_id) or {}
    if float(snap.get("remaining") or 0) + _EPS < q:
        raise _Err(f"Thùng {line.get('box_code')} chỉ còn {fmt_qty(snap.get('remaining') or 0)} — "
                   f"hàng trả đã được dùng, không gỡ được")
    conn.execute("DELETE FROM box_allocations WHERE id = ?", (row[0],))
    after = box_snapshot(conn, box_id)
    return {"return_in_removed": [dict(after, taken=q)] if after else []}


def _revert_disposed(conn, line: dict, fallback_id, actor: str) -> dict:
    did = line.get("disposal_id") or fallback_id
    if not did:
        return {}
    row = conn.execute("SELECT items, deleted_at FROM disposal_slips WHERE id = ?", (int(did),)).fetchone()
    if not row or row[1]:
        return {}
    items = _json.loads(row[0] or "[]")
    code, q = _line_code("disposed", line), parse_qty(line.get("quantity"))
    for i, it in enumerate(items):
        if str(it.get("product_code") or "").upper() == code and abs(parse_qty(it.get("quantity")) - q) < 1e-6:
            items.pop(i)
            break
    else:
        return {}
    if items:
        conn.execute("UPDATE disposal_slips SET items = ? WHERE id = ?",
                     (_json.dumps(items, ensure_ascii=False), int(did)))
    else:
        conn.execute("UPDATE disposal_slips SET items = ?, deleted_at = ?, deleted_by = ? WHERE id = ?",
                     (_json.dumps(items, ensure_ascii=False), _now_vn(), actor or "", int(did)))
    return {"disposal_id": int(did)}


def revert_goods_line(conn, return_id: int, kind: str, index: int, *, actor: str = "") -> tuple[dict | None, str | None]:
    """Gỡ dòng thứ `index` trong goods_result[kind]. Trả (extra, None) với extra =
    {line, kind, audit{deleted, return_in_removed}, disposal_id?, customer_key, reset},
    hoặc (None, 'not_found' | lỗi VN). All-or-nothing trong 1 transaction."""
    from return_store import ensure_returns_schema, get_return
    from utils.db import transaction
    if kind not in _KINDS:
        return None, "Loại dòng xử lý không hợp lệ"
    ensure_returns_schema(conn)
    try:
        with transaction(conn):
            r = get_return(conn, return_id)
            if not r or r.get("deleted_at"):
                return None, "not_found"
            res = r.get("goods_result") or {}
            lines = list(res.get(kind) or [])
            if not r.get("goods_handled_at") or not (0 <= index < len(lines)):
                return None, "Dòng xử lý hàng không còn — tải lại trang"
            line = lines[index]
            if kind == "restocked_new":
                extra = _revert_new_box(conn, return_id, line)
            elif kind == "restocked_existing":
                extra = _revert_existing(conn, return_id, line)
            else:
                extra = _revert_disposed(conn, line, res.get("disposal_id"), actor)
            lines.pop(index)
            res = {**res, kind: lines}
            reset = not any(res.get(k) for k in _KINDS)
            if reset:
                conn.execute("UPDATE return_slips SET goods_handled_at = NULL, goods_handled_by = NULL,"
                             " goods_result = NULL WHERE id = ?", (return_id,))
            else:
                conn.execute("UPDATE return_slips SET goods_result = ? WHERE id = ?",
                             (_json.dumps(res, ensure_ascii=False), return_id))
    except _Err as e:
        return None, str(e)
    audit = {"deleted": extra.get("deleted") or [], "return_in_removed": extra.get("return_in_removed") or []}
    return {"line": line, "kind": kind, "audit": audit, "disposal_id": extra.get("disposal_id"),
            "customer_key": r.get("customer_key"), "reset": reset}, None
