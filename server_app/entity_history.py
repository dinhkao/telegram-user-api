"""Lịch sử thao tác cho phiếu SX / thùng — đọc audit_events theo (scope, thread_id).

audit_middleware ghi mọi request kèm scope+entity_id (order/production/box). Ở đây
hiện MỌI thao tác GHI (POST/DELETE) + sự kiện tạo (*.created), dịch path→nhãn VN.
GET /api/media/{scope}/{entity_id}/history. Order dùng server_app/order_history.
"""
from __future__ import annotations

import asyncio
import json
import re

from aiohttp import web

from order_db import _get_connection
from server_app.order_history import _actor_display, _load_names

_NUM = re.compile(r"/-?\d+(?=/|$)")

_ACTION_LABELS = {"order.created": "Tạo đơn", "production.created": "Tạo phiếu SX",
                  "return.created": "Tạo phiếu trả", "return.invoiced": "Tạo HĐ KiotViet (trừ nợ)",
                  "return.invoice_deleted": "Xoá HĐ KiotViet (hoàn nợ)", "return.deleted": "Xoá phiếu trả",
                  # nhập hàng / nhà cung cấp (100% local)
                  "purchase.created": "Tạo phiếu nhập", "purchase.deleted": "Xoá phiếu nhập",
                  "supplier.created": "Tạo nhà cung cấp", "supplier.deleted": "Xoá nhà cung cấp",
                  # sản phẩm (event tường minh — mang id bất biến)
                  "product.created": "Tạo sản phẩm", "product.renamed": "Đổi mã SP",
                  "product.deleted": "Xoá sản phẩm", "product.linked": "Liên kết KiotViet",
                  "product.unlinked": "Gỡ liên kết KiotViet", "product.updated": "Sửa sản phẩm",
                  # quỹ (đã có event tường minh sẵn)
                  "quy.created": "Thu/chi quỹ", "quy.deleted": "Xoá phiếu quỹ",
                  # xuất hủy / kiểm kho
                  "disposal.created": "Tạo phiếu xuất hủy", "disposal.deleted": "Xoá phiếu hủy (hoàn tồn)",
                  "stocktake.created": "Tạo phiếu kiểm kho", "stocktake.completed": "Hoàn tất kiểm kho",
                  "stocktake.applied": "Áp dụng kiểm kho vào kho",
                  "adjustment.created": "Điều chỉnh tồn thùng", "adjustment.deleted": "Gỡ phiếu điều chỉnh (hoàn nguyên)",
                  # thao tác từ Telegram (bot nhóm) — trước đây vô hình ở web
                  "production.sp_changed": "Đổi sản phẩm (Telegram)",
                  "production.target_changed": "Đặt chỉ tiêu (Telegram)",
                  "production.report_saved": "Lưu báo cáo thợ (Telegram)",
                  "production.deleted_tg": "Xoá phiếu (Telegram)",
                  "customer.edited": "Sửa khách (Telegram)"}

# Biến động KHO (server_app/inventory_audit) — nhãn theo SCOPE + chi tiết từ payload.
_INV_ACTIONS = {"box.created", "box.allocated", "box.released", "box.moved", "box.moved_out",
                "box.moved_in", "box.deleted", "box.transfer_out", "box.transfer_in", "box.consumed",
                "box.disposed", "box.disposal_released"}


def _numv(v) -> str:
    try:
        return f"{float(v):g}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def _boxnum(code) -> str:
    """Số gọi ngắn của thùng: 'K2L-347' → '347'."""
    s = str(code or "")
    return s.split("-")[-1] or s


def _inv_entry(act: str, scope: str, p: dict) -> tuple[str, str] | None:
    """(nhãn, chi tiết) cho 1 event biến động kho, theo scope (box/place) + payload."""
    p = p or {}
    pc = p.get("product_code") or ""
    bc = _boxnum(p.get("box_code"))
    q = _numv(p.get("quantity"))
    head = " · ".join(x for x in [pc, f"thùng {bc}" if bc else ""] if x)
    join = lambda extra: " · ".join(x for x in [head, extra] if x)  # noqa: E731
    if act == "box.created":
        return ("Nhập thùng vào kho" if scope == "place" else "Tạo thùng"), join(f"{q} cây" if q else "")
    if act in ("box.allocated", "box.released"):
        taken = _numv(p.get("taken"))
        verb = "lấy" if act == "box.allocated" else "trả"
        rem = _numv(p.get("remaining")) if p.get("remaining") is not None else ""
        # order_text KHÔNG nhét vào detail — History render nó thành LINK tới đơn (item['order'])
        extra = " · ".join(x for x in [f"{verb} {taken}" if taken else "", f"thùng còn {rem}" if rem != "" else ""] if x)
        return ("Xuất cho đơn" if act == "box.allocated" else "Thu hồi về kho"), join(extra)
    if act == "box.moved":   # lịch sử THÙNG — ghi rõ TỪ → ĐẾN
        return "Chuyển kho", join(f"từ {p.get('from_name') or 'Chưa xếp'} → {p.get('to_name') or 'Chưa xếp'}")
    if act == "box.moved_out":
        return "Thùng chuyển đi", join(f"→ {p.get('to_name') or 'Chưa xếp'}")
    if act == "box.moved_in":
        return "Thùng chuyển đến", join(f"từ {p.get('from_name') or 'Chưa xếp'}")
    if act == "box.consumed":
        taken = _numv(p.get("taken"))
        tgt = p.get("target_code") or ""
        extra = " · ".join(x for x in [f"tiêu hao {taken}" if taken else "", f"đóng gói {tgt}" if tgt else ""] if x)
        return "Tiêu hao đóng gói", join(extra)
    if act in ("box.disposed", "box.disposal_released"):
        taken = _numv(p.get("taken"))
        rem = _numv(p.get("remaining")) if p.get("remaining") is not None else ""
        reason = str(p.get("disposal_reason") or "").strip()
        verb = "hủy" if act == "box.disposed" else "hoàn"
        extra = " · ".join(x for x in [f"{verb} {taken}" if taken else "", f"thùng còn {rem}" if rem != "" else "", reason] if x)
        return ("Xuất hủy" if act == "box.disposed" else "Hoàn xuất hủy"), join(extra)
    if act == "box.deleted":
        return "Xoá thùng khỏi kho", join("")
    if act in ("box.transfer_out", "box.transfer_in"):
        out = act == "box.transfer_out"
        peer = _boxnum(p.get("to_box") or p.get("to_code") if out else p.get("from_box") or p.get("from_code"))
        arrow = f"{'→' if out else 'từ'} thùng {peer}" if peer else ""
        extra = " · ".join(x for x in [arrow, q] if x)
        return ("Chuyển hàng sang thùng khác" if out else "Nhận hàng từ thùng khác"), join(extra)
    return None

_SOURCE_LABELS = {
    "POST /api/production/{id}/product": "Đổi sản phẩm",
    "POST /api/production/{id}/target": "Đặt chỉ tiêu",
    "POST /api/production/{id}/note": "Sửa ghi chú",
    "POST /api/production/{id}/number": "Thêm số",
    "POST /api/production/{id}/boxes": "Nhập thùng",
    "POST /api/production/{id}/report": "Lưu báo cáo thợ",
    "POST /api/production/{id}/kind": "Đổi loại phiếu",
    "DELETE /api/production/{id}": "Xoá phiếu",
    "POST /api/inventory/box/{id}": "Sửa thùng",
    "POST /api/inventory/box/{id}/disable": "Vô hiệu / kích hoạt thùng",
    "POST /api/returns/{id}/update": "Sửa hàng trả",
    "POST /api/purchases/{id}/update": "Sửa phiếu nhập",
    "POST /api/suppliers/{id}": "Sửa nhà cung cấp",
    "POST /api/returns/{id}/invoice": "Tạo HĐ KiotViet (trừ nợ)",
    "POST /api/returns/{id}/delete": "Xoá phiếu trả",
    # sản phẩm / phiếu SX bổ sung
    "POST /api/production/{id}/slip-lock": "Khoá phiếu (admin)",
    "POST /api/production/{id}/slip-unlock": "Mở khoá phiếu (admin)",
    "POST /api/products/{id}": "Sửa sản phẩm",
    "DELETE /api/products/{id}": "Xoá sản phẩm",
    # khách hàng (POST update phân loại theo body ở dưới)
    "POST /api/customers/{id}/link-kiotviet": "Liên kết KiotViet",
    "POST /api/customers/{id}/unlink-kiotviet": "Gỡ liên kết KiotViet",
    "DELETE /api/customers/{id}": "Xoá khách",
    # việc (POST update phân loại theo body ở dưới)
    "DELETE /api/tasks/{id}": "Xoá việc",
    # vị trí (POST update phân loại theo body ở dưới)
    "DELETE /api/places/{id}": "Xoá vị trí",
    # đơn vị chứa / thợ / bảng giá
    "DELETE /api/units/{id}": "Xoá đơn vị chứa",
    "POST /api/workers/{id}": "Sửa thợ",
    "DELETE /api/workers/{id}": "Xoá thợ",
    "POST /api/workers/reorder": "Sắp xếp thợ",
    "POST /api/price-lists/{id}": "Lưu bảng giá",
    "POST /api/price-lists/{id}/price": "Sửa 1 giá SP",
}
_SKIP = {"POST /api/production/{id}/report/parse",   # xem trước, không phải ghi
         "POST /api/returns/{id}/invoice",           # đã có event return.invoiced
         "POST /api/returns/{id}/delete",            # đã có event return.deleted
         "POST /api/returns/{id}/delete-invoice",    # đã có event return.invoice_deleted
         "POST /api/purchases/{id}/delete",          # đã có event purchase.deleted
         "POST /api/purchases/{id}/pay",             # đã có event purchase.paid
         "POST /api/purchases/{id}/payments/{id}/delete",  # đã có event purchase.payment_deleted
         "POST /api/suppliers/{id}/delete"}          # đã có event supplier.deleted


def _box_update_action(bd: dict, places: dict) -> tuple[str, str] | None:
    """(label, detail) cho POST /api/inventory/box/{id} theo BODY — 1 endpoint sửa
    nhiều thứ nên phân loại để lịch sử đọc được: Chuyển kho / Ghi chú / NSX / Đơn vị."""
    if not isinstance(bd, dict):
        return None
    if "place_id" in bd:
        pid = bd.get("place_id")
        name = places.get(int(pid)) if isinstance(pid, (int, float, str)) and str(pid).strip().isdigit() else None
        return "Chuyển kho", f"→ {name or 'Chưa xếp'}"
    if "unit_id" in bd:
        return "Đổi đơn vị chứa", ""
    if "mfg_date" in bd:
        return "Sửa ngày SX", str(bd.get("mfg_date") or "")[:20]
    if "note" in bd:
        return "Sửa ghi chú", str(bd.get("note") or "")[:50]
    return None


def _customer_update_action(bd: dict) -> tuple[str, str] | None:
    """POST /api/customers/{id} sửa nhiều thứ → phân loại theo body."""
    if not isinstance(bd, dict):
        return None
    if "personal_price_list" in bd:
        return "Sửa bảng giá riêng", ""
    if "detectPatterns" in bd or "patterns" in bd:
        return "Sửa từ khoá nhận diện", ""
    if "default_tasks" in bd:
        return "Sửa việc mặc định", ""
    if "note" in bd or "ghi_chu" in bd:
        return "Sửa ghi chú khách", str(bd.get("note") or bd.get("ghi_chu") or "")[:50]
    if "price_list" in bd:
        return "Đổi bảng giá", ""
    return "Sửa khách", ""


def _task_update_action(bd: dict) -> tuple[str, str] | None:
    if not isinstance(bd, dict):
        return None
    if "done" in bd:
        return ("Đánh dấu xong" if bd.get("done") else "Mở lại việc"), ""
    if "assignee" in bd:
        return "Giao việc", str(bd.get("assignee") or "")[:30]
    if any(k in bd for k in ("title", "note", "due_at")):
        return "Sửa việc", str(bd.get("title") or "")[:40]
    return "Cập nhật việc", ""


def _place_update_action(bd: dict) -> tuple[str, str] | None:
    if not isinstance(bd, dict):
        return None
    if "name" in bd:
        return "Đổi tên vị trí", str(bd.get("name") or "")[:40]
    if "note" in bd:
        return "Sửa ghi chú vị trí", str(bd.get("note") or "")[:50]
    return "Sửa vị trí", ""


def _report_detail(text: str) -> str:
    """Tóm tắt báo cáo thợ cho lịch sử: '14 thợ · tổng 489,5 · 1/7/2026' thay vì
    dump 50 ký tự đầu của text dạng ';' (nhìn như rác)."""
    try:
        from production_store.domain import parse_report
        p = parse_report(text)
        rows = [r for r in p.get("rows", []) if str(r.get("name") or "").strip()]
        if not rows:
            return ""
        total = sum(r.get("tong_sheet") or 0 for r in rows)
        total_s = f"{total:g}".replace(".", ",")
        parts = [f"{len(rows)} thợ", f"tổng {total_s}"]
        if p.get("date"):
            parts.append(str(p["date"]))
        return " · ".join(parts)
    except Exception:
        return ""


def _norm(source: str):
    """'POST /api/production/40643/note?x=1' → (method, 'POST /api/production/{id}/note', path)."""
    method, _, rest = source.partition(" ")
    path = _NUM.sub("/{id}", rest.split("?")[0])
    return method, f"{method} {path}", path


def _label(key: str, method: str, path: str) -> str:
    if key in _SOURCE_LABELS:
        return _SOURCE_LABELS[key]
    if path.endswith("/comments"):
        return "Bình luận"
    if path.endswith("/images") and method == "POST":
        return "Thêm ảnh"
    if "/images/" in path and method == "DELETE":
        return "Xoá ảnh"
    if method == "DELETE":
        return "Xoá"
    seg = path.rstrip("/").rsplit("/", 1)[-1]
    return "Thao tác" if seg in ("", "{id}") else f"Thao tác: {seg}"


def get_entity_history(scope: str, entity_id: int, limit: int = 60) -> list[dict]:
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT ts, actor_id, action, source, payload_json, result_json FROM audit_events "
            "WHERE scope = ? AND thread_id = ? ORDER BY id DESC LIMIT 300",
            (scope, int(entity_id)),
        ).fetchall()
        names = _load_names()
        try:   # map vị trí kho cho label "Chuyển kho → Kho B" (bảng có thể chưa tạo)
            places = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM inventory_places").fetchall()}
        except Exception:
            places = {}
        box_src = None   # phiếu SX tạo ra thùng này (chỉ scope box) → link ở event "Tạo thùng"
        if scope == "box":
            try:
                rr = conn.execute("SELECT source_thread_id FROM inventory_boxes WHERE id = ?", (int(entity_id),)).fetchone()
                box_src = rr[0] if rr else None
            except Exception:
                box_src = None
        from server_app.event_format import event_entry
        from server_app.history_format import Resolver, href_for, part, parts_text
        resolver = Resolver(conn)
        out: list[dict] = []
        for r in rows:
            act = r["action"]
            if act != "http.request":
                try:
                    pl = json.loads(r["payload_json"] or "{}")
                except Exception:
                    pl = {}
                pl = pl if isinstance(pl, dict) else {}
                ent = event_entry(act, pl, resolver)
                if ent:
                    label, parts = ent
                    if not parts and pl.get("detail"):   # event Telegram cũ mang detail sẵn
                        parts = [part(str(pl["detail"])[:80])]
                elif act in _ACTION_LABELS:
                    label, parts = _ACTION_LABELS[act], []
                elif act in _INV_ACTIONS:
                    lg = _inv_entry(act, scope, pl)
                    if not lg:
                        continue
                    label, parts = lg[0], ([part(lg[1])] if lg[1] else [])
                else:
                    continue   # event lạ không thuộc lịch sử thực thể
                # scope place: nhãn "Tạo thùng" đọc là nhập kho
                if act == "box.created":
                    label = "Nhập thùng vào kho" if scope == "place" else "Tạo thùng"
                    if box_src:   # link → phiếu SX nguồn
                        parts = parts + [part(" · "), part("phiếu SX →", href_for("production", box_src))]
                if act in ("box.allocated", "box.released") and scope == "place":
                    label = "Xuất cho đơn" if act == "box.allocated" else "Thu hồi về kho"
                out.append({"ts": r["ts"], "actor": _actor_display(r["actor_id"], names),
                            "action": label, "detail": parts_text(parts), "parts": parts,
                            "changes": [], "ok": True})
            elif act == "http.request":
                source = r["source"] or ""
                if not (source.startswith("POST ") or source.startswith("DELETE ")):
                    continue
                method, key, path = _norm(source)
                if key in _SKIP:
                    continue
                is_report = path.endswith("/report")
                detail = ""
                label_override = None
                skip_row = False
                try:
                    b = json.loads(r["payload_json"] or "{}").get("body")
                    if isinstance(b, str) and b.strip().startswith("{"):
                        bd = json.loads(b)
                        if is_report:
                            detail = _report_detail(str(bd.get("text") or ""))
                        elif key == "POST /api/inventory/box/{id}":
                            # Chuyển kho: bỏ dòng này — đã có event box.moved (ghi TỪ → ĐẾN)
                            if "place_id" in bd or bd.get("clear_place"):
                                skip_row = True
                            else:
                                la = _box_update_action(bd, places)
                                if la:
                                    label_override, detail = la
                        elif key == "POST /api/customers/{id}":
                            la = _customer_update_action(bd)
                            if la:
                                label_override, detail = la
                        elif key == "POST /api/tasks/{id}":
                            la = _task_update_action(bd)
                            if la:
                                label_override, detail = la
                        elif key == "POST /api/places/{id}":
                            la = _place_update_action(bd)
                            if la:
                                label_override, detail = la
                        else:
                            detail = str(bd.get("text") or bd.get("note") or "")[:50]
                except Exception:
                    detail = ""
                if skip_row:
                    continue
                try:
                    status = json.loads(r["result_json"] or "{}").get("status")
                except Exception:
                    status = None
                actor = _actor_display(r["actor_id"], names)
                ok = status is None or (isinstance(status, int) and 200 <= status < 300)
                # Tự-lưu báo cáo mỗi ~1.5s → hàng chục event liền nhau. Gộp các lần
                # "Lưu báo cáo thợ" LIÊN TIẾP của cùng người: giữ bản MỚI nhất.
                if is_report and ok and out and out[-1].get("_rk") == (actor,):
                    continue
                out.append({"ts": r["ts"], "actor": actor,
                            "action": label_override or _label(key, method, path), "detail": detail,
                            "parts": [part(detail)] if detail else [], "changes": [],
                            "ok": ok, **({"_rk": (actor,)} if is_report and ok else {})})
            else:
                continue
            if len(out) >= limit:
                break
        for e in out:
            e.pop("_rk", None)   # khoá nội bộ để gộp — không trả ra ngoài
        return out
    except Exception:
        return []
    finally:
        conn.close()


async def entity_history_handler(request: web.Request):
    scope = request.match_info.get("scope", "")
    if scope not in ("production", "box", "return", "task", "place",
                     "customer", "product", "unit", "worker", "price", "quy",
                     "supplier", "purchase", "disposal", "stocktake"):
        return web.json_response({"ok": False, "error": "scope không hợp lệ"}, status=400)
    try:
        entity_id = int(request.match_info.get("entity_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "entity_id không hợp lệ"}, status=400)
    history = await asyncio.to_thread(get_entity_history, scope, entity_id)
    return web.json_response({"ok": True, "history": history})
