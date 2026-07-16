"""HTTP handlers kho thùng (webapp) — /api/inventory* + nhập/xuất thùng.

Nhập thùng từ phiếu SX (POST /api/production/{id}/boxes) → tạo box rows + append
numbers[] cho slip (total/progress tự đúng). Xem tồn theo product (GET /api/inventory,
/api/inventory/{code}). Xuất/thu thùng cho đơn (POST /api/order/{id}/allocate|release).

Nối: inventory_store, production_store (add_number/get_slip), server_app.realtime,
server_app.production_routes (_web_actor), utils.db. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from aiohttp import web

from inventory_store import (
    create_inventory_table,
    migrate_inventory_table,
    create_allocations_table,
    migrate_legacy_allocations,
    add_boxes,
    list_boxes,
    product_summary,
    get_box,
    update_box,
    set_disabled,
    delete_box,
    list_places,
    add_place,
    rename_place,
    delete_place,
    list_units,
    add_unit,
    delete_unit,
    allocate_picks,
    fifo_consume,
    list_order_allocations,
    list_box_allocations,
    get_allocation,
    delete_allocation,
    summarize,
)
from recipe_store import create_recipe_table, list_recipe, set_recipe_line, delete_recipe_line, recipe_needs
from production_store import get_slip, add_number, set_total, remove_number_by_note
from order_store.serialization import get_order_by_thread_id
from server_app.production_routes import _web_actor
from utils.db import get_connection


def _order_first_line(conn, thread_id) -> str:
    """Dòng đầu nội dung đơn (sneak peek cho danh sách đơn đã xuất). Rỗng nếu không có."""
    if not thread_id:
        return ""
    o = get_order_by_thread_id(conn, thread_id)
    if not o:
        return ""
    txt = (o.get("text") or o.get("text_raw") or "").strip()
    return txt.split("\n", 1)[0].strip()[:80] if txt else ""


def _conn():
    return get_connection()


def _ensure(conn):
    """Tạo bảng + migrate (cột mới như disabled/mfg_date, bảng box_allocations)."""
    create_inventory_table(conn)
    migrate_inventory_table(conn)
    create_allocations_table(conn)
    migrate_legacy_allocations(conn)
    create_recipe_table(conn)


def _thread_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return None


def _product_code(request: web.Request) -> str:
    return str(request.match_info.get("product_code", "")).strip().upper()


# Các event thực sự làm TỔNG TỒN của sản phẩm thay đổi. Chuyển vị trí/chuyển giữa
# hai thùng không đưa sản phẩm lên đầu vì tổng tồn vẫn giữ nguyên.
_STOCK_CHANGE_ACTIONS = (
    "box.created", "box.allocated", "box.released", "box.consumed",
    "box.disposed", "box.disposal_released", "box.deleted",
)


def _time_key(value) -> float:
    """Mọi kiểu ISO trong DB (Z, +07:00, legacy có dấu cách) → epoch để so đúng TZ."""
    if not value:
        return 0
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        # Mốc legacy "YYYY-MM-DD HH:MM:SS" do SQLite datetime('now') lưu UTC.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return 0


def _latest_stock_changes(conn) -> dict[str, str]:
    """{MÃ SP: thời gian biến động tồn gần nhất} từ audit.

    Đọc các action qua index action rồi gộp ở Python để không phụ thuộc hàm JSON
    riêng của SQLite/Postgres. Bảng audit có thể vắng trong test DB cũ → fallback
    im lặng sang mốc tạo thùng/phân bổ do product_summary trả về.
    """
    marks = ",".join("?" for _ in _STOCK_CHANGE_ACTIONS)
    try:
        rows = conn.execute(
            f"SELECT ts, payload_json FROM audit_events WHERE action IN ({marks})",
            _STOCK_CHANGE_ACTIONS,
        ).fetchall()
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        code = str(payload.get("product_code") or "").strip().upper() if isinstance(payload, dict) else ""
        at = row["ts"]
        if code and _time_key(at) > _time_key(out.get(code)):
            out[code] = at
    return out


# ─── nhập thùng (từ phiếu SX) ─────────────────────────────────────────────────
async def production_add_boxes_handler(request: web.Request):
    """Nhập 1 đợt = N thùng, mỗi thùng số cây tự do. Mã thùng tự sinh theo product."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    from server_app.production_lock import locked_error as _prod_locked_error
    lk = await _prod_locked_error(request, thread_id)   # phiếu khoá 24h → cấm nhập thùng
    if lk:
        return lk
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = body.get("boxes")
    if not isinstance(raw, list) or not raw:
        return web.json_response({"ok": False, "error": "Thiếu danh sách thùng"}, status=400)
    quantities = []
    for item in raw:
        try:
            q = float(item.get("quantity") if isinstance(item, dict) else item)
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "Số lượng thùng không hợp lệ"}, status=400)
        if q <= 0:
            return web.json_response({"ok": False, "error": "Số lượng thùng phải > 0"}, status=400)
        quantities.append(q)
    note = str(body.get("note") or "").strip()
    mfg_date = str(body.get("mfg_date") or "").strip() or None
    try:
        unit_id = int(body["unit_id"]) if body.get("unit_id") else None
    except (TypeError, ValueError):
        unit_id = None
    try:
        place_id = int(body["place_id"]) if body.get("place_id") else None
    except (TypeError, ValueError):
        place_id = None
    actor = _web_actor(request, body)
    snaps: list = []       # ảnh chụp thùng mới (cho audit box + place)
    mat_snaps: list = []   # ảnh chụp thùng NL đã tiêu hao (cho audit tiêu hao)
    pack_ctx: dict = {}    # {code} = SP thành phẩm đóng gói (cho event tiêu hao)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            slip = get_slip(conn, thread_id)
            # Cho phép nhập thùng cho SP BẤT KỲ (không chỉ sp_name của phiếu) → 1 phiếu
            # SX có thể tạo thùng cho nhiều SP. Mặc định = sp_name của phiếu.
            req_code = str(body.get("product_code") or "").strip().upper()
            code = req_code or str((slip or {}).get("sp_name") or "").strip().upper()
            if not slip or not code:
                return None, None, None
            # Nguyên liệu theo LOẠI PHIẾU: sản xuất → KHÔNG cần NL (SP đầu ra là
            # nguyên liệu, đánh dấu is_material); đóng gói → BẮT BUỘC có công thức
            # và chọn đủ thùng NL cho MỌI nguyên liệu TRƯỚC khi tạo thùng.
            kind = (slip or {}).get("kind") or "san_xuat"
            # SP tự-là-thùng (KDXDB5/KGL5): bản thân là 1 thùng → mỗi thùng = 1 dòng
            # quantity=1, KHÔNG có đơn vị chứa. Enforce server-side (chốt thật).
            from product_store import get_product as _gp
            _prod = _gp(conn, code)
            self_container = bool(_prod and _prod.get("self_container"))
            qtys = [1.0] * len(quantities) if self_container else quantities
            uid = None if self_container else unit_id
            # Thùng NL người dùng chọn để tiêu hao (body.consume = [{box_id, quantity}]).
            raw_picks = body.get("consume") if isinstance(body.get("consume"), list) else []
            picks = [p for p in raw_picks if isinstance(p, dict) and p.get("box_id")]
            # Admin bật: cho nhập trực tiếp SP đóng gói KHÔNG bắt buộc trừ NL → bỏ mọi gate NL.
            from settings_store import get_bool
            allow_no_mat = get_bool("pack_allow_no_material", False)
            if kind == "dong_goi" and not allow_no_mat:
                # Kiểm tra theo tổng cây dự kiến của đợt này.
                needs = recipe_needs(conn, code, sum(qtys))
                if not needs:
                    return "norecipe", code, None
                # mã NL của từng thùng chọn (COALESCE mã hiện hành)
                codes: dict = {}
                for p in picks:
                    row = conn.execute(
                        "SELECT COALESCE(pr.code, b.product_code) FROM inventory_boxes b "
                        "LEFT JOIN products pr ON pr.id = b.product_id WHERE b.id = ?",
                        (p.get("box_id"),)).fetchone()
                    if row:
                        codes[p.get("box_id")] = row[0]
                got: dict = {}
                for p in picks:
                    c = codes.get(p.get("box_id"))
                    if c is None:
                        continue
                    try:
                        got[c] = got.get(c, 0.0) + float(p.get("quantity") or 0)
                    except (TypeError, ValueError):
                        pass
                # TỐI THIỂU: phải chọn đủ nhu cầu công thức
                for nd in needs:
                    if got.get(nd["code"], 0.0) + 1e-6 < nd["amount"]:
                        return "short", nd["code"], nd["amount"]
                # TỐI ĐA: KHÔNG cho tiêu hao quá nhu cầu (ratio × số cây). Trim cộng dồn
                # theo mã → chặn trừ dư khi client gửi số cũ (vd đổi số cây sau khi chọn
                # thùng). Mã ngoài công thức giữ nguyên. Đây là chốt chặn thật (bug thùng 322).
                remain_allow = {nd["code"]: nd["amount"] for nd in needs}
                capped: list = []
                for p in picks:
                    c = codes.get(p.get("box_id"))
                    try:
                        q = float(p.get("quantity") or 0)
                    except (TypeError, ValueError):
                        continue
                    if c in remain_allow:
                        allow = remain_allow[c]
                        if allow <= 1e-9:
                            continue          # đã đủ nhu cầu → bỏ phần dư
                        take = min(q, allow)
                        if take <= 1e-9:
                            continue
                        remain_allow[c] = allow - take
                        capped.append({**p, "quantity": round(take, 6)})
                    else:
                        capped.append(p)      # mã ngoài công thức → không cap
                picks = capped
            elif kind == "san_xuat" and not allow_no_mat:
                # phiếu SẢN XUẤT chỉ nhập được SP có thể SX trực tiếp (can_produce_directly)
                from product_store import get_product
                prod = get_product(conn, code)
                if prod is not None and not prod.get("can_produce_directly"):
                    return "notdirect", code, None
            try:
                created = add_boxes(conn, code, qtys, source_thread_id=thread_id, by=actor, note=note, mfg_date=mfg_date, unit_id=uid, place_id=place_id)
            except ValueError as e:   # hết 999 số gọi đang hoạt động (thực tế khó xảy ra)
                return "full", str(e), None
            # đồng bộ slip.total/numbers/progress: 1 entry/thùng (note = mã thùng)
            total = slip.get("total") or 0
            for box in created:
                total = add_number(conn, thread_id, box["quantity"], f"📦 {box['box_code']}", by=actor)
            # Trừ kho NL (kind='production') — đã validate đủ ở trên.
            consume = allocate_picks(conn, picks, thread_id, by=actor, kind="production") if picks else []
            from server_app.inventory_audit import box_snapshot
            snaps.extend(s for b in created if (s := box_snapshot(conn, b.get("id"))))
            # ảnh chụp thùng NL đã tiêu hao (remaining SAU trừ) → ghi lịch sử thùng NL
            for p in picks:
                if (ms := box_snapshot(conn, p.get("box_id"))):
                    ms["consumed_amount"] = float(p.get("quantity") or 0)
                    mat_snaps.append(ms)
            pack_ctx["code"] = code
            return created, total, consume
        finally:
            conn.close()
    created, total, consume = await asyncio.to_thread(_run)
    if created is None:
        return web.json_response({"ok": False, "error": "Chưa có sản phẩm, chưa nhập thùng được"}, status=400)
    if created == "short":
        return web.json_response({"ok": False, "error": f"Chưa chọn đủ thùng nguyên liệu {total} (cần {consume:g})"}, status=400)
    if created == "norecipe":
        return web.json_response({"ok": False, "error": f"Phiếu đóng gói bắt buộc trừ nguyên liệu — {total} chưa có công thức. Thêm công thức ở trang chi tiết sản phẩm."}, status=400)
    if created == "notdirect":
        return web.json_response({"ok": False, "error": f"SP {total} không sản xuất trực tiếp — chỉ nhập được qua phiếu ĐÓNG GÓI (trừ nguyên liệu). Đổi loại phiếu, hoặc bật 'SX trực tiếp' ở chi tiết SP."}, status=400)
    if created == "full":
        return web.json_response({"ok": False, "error": total}, status=400)
    from server_app.realtime import emit_inventory_changed, emit_production_changed
    emit_production_changed(thread_id)
    emit_inventory_changed()
    # Lịch sử: mỗi thùng mới → event box.created (lịch sử THÙNG + lịch sử VỊ TRÍ)
    from server_app.inventory_audit import log_boxes_created, log_boxes_consumed
    _atype = "web_user" if request.get("web_user") else "http_client"
    log_boxes_created(snaps, actor=actor, actor_type=_atype)
    if mat_snaps:   # NL tiêu hao để đóng gói → lịch sử thùng NL + vị trí NL
        log_boxes_consumed(mat_snaps, target_code=pack_ctx.get("code"), slip_id=thread_id, actor=actor, actor_type=_atype)
    # Các phần nguyên liệu đã tiêu hao (allocate_picks kind='production') — client hiện tóm tắt
    return web.json_response({"ok": True, "boxes": created, "total": total, "consumed": consume or []})


async def recipe_get_handler(request: web.Request):
    """Công thức (nguyên liệu) của 1 SP + tồn hiện tại của từng nguyên liệu."""
    code = _product_code(request)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            lines = list_recipe(conn, code)
            # gắn tồn hiện tại (remaining) + đơn vị của mỗi nguyên liệu (lọc theo product_id)
            from inventory_store.queries import _pid_filter
            from product_store import resolve_code
            for ln in lines:
                frag, ps = _pid_filter(conn, ln["ingredient_code"])
                row = conn.execute(
                    "SELECT COALESCE(SUM(b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0)),0) AS rem "
                    f"FROM inventory_boxes b WHERE {frag} AND (b.disabled IS NULL OR b.disabled=0)",
                    ps,
                ).fetchone()
                ln["stock"] = row[0]
                ing = resolve_code(conn, ln["ingredient_code"])
                ln["unit"] = (ing.get("unit") if ing else None) or "cây"
            prod = resolve_code(conn, code)
            return lines, (prod.get("unit") if prod else None) or "cây", bool((prod or {}).get("self_container"))
        finally:
            conn.close()
    lines, unit, self_container = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "recipe": lines, "unit": unit, "self_container": self_container})


async def recipe_set_handler(request: web.Request):
    """Thêm/sửa 1 nguyên liệu. Body {ingredient_code, ratio}."""
    code = _product_code(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    ic = str(body.get("ingredient_code") or "").strip().upper()
    ratio = body.get("ratio")
    if not ic:
        return web.json_response({"ok": False, "error": "Thiếu mã nguyên liệu"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return set_recipe_line(conn, code, ic, ratio)
        finally:
            conn.close()
    line = await asyncio.to_thread(_run)
    if not line:
        return web.json_response({"ok": False, "error": "Nguyên liệu/tỉ lệ không hợp lệ (không tự làm nguyên liệu, tỉ lệ > 0)"}, status=400)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True, "line": line})


async def recipe_delete_handler(request: web.Request):
    """Xoá 1 dòng công thức theo id."""
    try:
        lid = int(request.match_info.get("line_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "line_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            delete_recipe_line(conn, lid)
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True})


async def production_boxes_list_handler(request: web.Request):
    """Các thùng đã nhập ở 1 phiếu SX (mọi status) — cho list + deep-link focus."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return list_boxes(conn, source_thread_id=thread_id)
        finally:
            conn.close()
    boxes = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "boxes": boxes})


# ─── xem tồn kho ──────────────────────────────────────────────────────────────
async def inventory_list_handler(request: web.Request):
    """Dashboard kho: MỌI mã SP (từ product_store) — có thùng thì kèm tồn/đếm, chưa có
    thì tồn 0. Kèm tên danh mục + cờ liên kết KiotViet + mốc biến động tồn mới nhất.
    Giữ thứ tự API cũ (tồn giảm dần); riêng dashboard #/kho sắp lại theo mốc này."""
    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            summ = product_summary(conn)   # chỉ product CÓ thùng
            audit_changes = _latest_stock_changes(conn)
            from product_store.queries import get_all_products
            prods = get_all_products(conn)
        finally:
            conn.close()
        by_code = {s["product_code"]: dict(s) for s in summ}
        meta = {p["code"]: (p.get("name") or p.get("kv_full_name") or "", bool(p.get("kv_id")), p.get("unit") or "cây") for p in prods}
        # thêm product chưa có thùng (tồn 0)
        for p in prods:
            by_code.setdefault(p["code"], {
                "product_code": p["code"], "product_id": p.get("id"),
                "in_stock_total": 0, "in_stock_count": 0,
                "allocated_count": 0, "shipped_count": 0, "total_count": 0,
            })
        rows = []
        for code, s in by_code.items():
            name, linked, unit = meta.get(code, ("", False, "cây"))
            # Audit cover cả thu hồi/xuất hủy/xoá; hai mốc SQL là fallback cho dữ liệu
            # trước thời audit hoặc event async chưa ghi xong ngay lúc response chạy.
            candidates = [audit_changes.get(code), s.pop("last_box_at", None), s.pop("last_allocated_at", None)]
            last_changed_at = max(candidates, key=_time_key) if any(candidates) else None
            rows.append({**s, "name": name, "linked": linked, "unit": unit,
                         "last_changed_at": last_changed_at})
        rows.sort(key=lambda r: (-(r.get("in_stock_total") or 0), r["product_code"]))
        return rows
    products = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "products": products})


async def unplaced_count_handler(request: web.Request):
    """Đếm thùng CHƯA XẾP KHO (chưa gán vị trí): active + còn hàng + place_id NULL.
    Query nhẹ cho banner chạy chữ ở webapp (main.tsx NopBanner)."""
    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            row = conn.execute(
                "SELECT COUNT(*) FROM inventory_boxes b "
                "WHERE COALESCE(b.disabled,0)=0 AND b.place_id IS NULL "
                "AND (b.quantity - COALESCE((SELECT SUM(a.quantity) FROM box_allocations a WHERE a.box_id=b.id),0)) > 0"
            ).fetchone()
            return int(row[0] or 0)
        finally:
            conn.close()
    n = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "count": n})


def _box_summary(b: dict) -> dict:
    """Payload gọn dùng cho lưới kho; giữ capacity để mọi màn hình vẽ cùng mức đầy."""
    return {
        "id": b["id"], "product_code": b["product_code"], "box_code": b["box_code"],
        "quantity": b.get("quantity") or 0, "remaining": b.get("remaining") or 0,
        "capacity": b.get("capacity") if b.get("capacity") is not None else (b.get("quantity") or 0),
        "allocated": b.get("allocated") or 0, "disabled": bool(b.get("disabled")),
        "reserved": bool(b.get("reserved")),
        "note": b.get("note") or "", "mfg_date": b.get("mfg_date"), "created_at": b.get("created_at"),
        "place_id": b.get("place_id"), "place_name": b.get("place_name"),
        "unit_id": b.get("unit_id"), "unit_name": b.get("unit_name"),
        "product_unit": b.get("product_unit") or "cây",
        "source_thread_id": b.get("source_thread_id"),
    }


async def all_boxes_handler(request: web.Request):
    """Kho hàng: MỌI thùng của MỌI sản phẩm (để dashboard kho trực quan + lọc theo mã).
    Trả list gọn; client gom nhóm theo product_code + lọc."""
    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            boxes = list_boxes(conn)   # không lọc = tất cả
        finally:
            conn.close()
        return boxes
    boxes = await asyncio.to_thread(_run)
    out = [_box_summary(b) for b in boxes]
    return web.json_response({"ok": True, "boxes": out})


async def units_list_handler(request: web.Request):
    """Danh sách đơn vị chứa (Thùng/Bọc/Cây/Kiện/Kệ…) + số thùng dùng mỗi đơn vị."""
    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return list_units(conn)
        finally:
            conn.close()
    return web.json_response({"ok": True, "units": await asyncio.to_thread(_run)})


async def unit_create_handler(request: web.Request):
    """Tạo đơn vị mới. Body {name}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "Thiếu tên đơn vị"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return add_unit(conn, name)
        finally:
            conn.close()
    unit = await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True, "unit": unit})


async def unit_delete_handler(request: web.Request):
    """Xoá 1 đơn vị — CHỈ admin."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá đơn vị"}, status=403)
    try:
        uid = int(request.match_info.get("unit_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "unit_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            delete_unit(conn, uid)
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed, emit_box_changed
    emit_inventory_changed()
    emit_box_changed()
    return web.json_response({"ok": True})


async def places_list_handler(request: web.Request):
    """Danh sách vị trí kho (Kho A, Kho B…) + số thùng + ảnh mới nhất (thumb card)."""
    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            places = list_places(conn)
        finally:
            conn.close()
        from entity_media_store import latest_image_ids
        thumbs = latest_image_ids("place", [p["id"] for p in places])
        for p in places:
            p["thumb_image_id"] = thumbs.get(p["id"])
        return places
    return web.json_response({"ok": True, "places": await asyncio.to_thread(_run)})


async def place_create_handler(request: web.Request):
    """Tạo vị trí kho mới. Body {name, note?}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "Thiếu tên vị trí"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return add_place(conn, name, body.get("note") or "")
        finally:
            conn.close()
    place = await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True, "place": place})


async def place_rename_handler(request: web.Request):
    """Sửa 1 vị trí kho: tên và/hoặc ghi chú. Body {name?, note?}."""
    try:
        pid = int(request.match_info.get("place_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "place_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip() if "name" in body else None
    note = str(body.get("note") or "") if "note" in body else None
    if "name" in body and not name:
        return web.json_response({"ok": False, "error": "Thiếu tên vị trí"}, status=400)
    if name is None and note is None:
        return web.json_response({"ok": False, "error": "Không có gì để sửa"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return rename_place(conn, pid, name=name, note=note)
        finally:
            conn.close()
    place = await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed, emit_box_changed
    emit_inventory_changed()
    emit_box_changed()
    return web.json_response({"ok": True, "place": place})


async def place_delete_handler(request: web.Request):
    """Xoá 1 vị trí kho — CHỈ admin. Thùng đang ở đó gỡ liên kết."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá vị trí"}, status=403)
    try:
        pid = int(request.match_info.get("place_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "place_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            delete_place(conn, pid)
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed, emit_box_changed
    emit_inventory_changed()
    emit_box_changed()
    return web.json_response({"ok": True})


async def box_delete_handler(request: web.Request):
    """Xoá HẲN 1 thùng — CHỈ admin. Cấm nếu đã xuất phần nào cho đơn (thu hồi trước)."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá thùng"}, status=403)
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    del_snap: dict = {}   # ảnh chụp thùng bị xoá → ghi lịch sử vị trí

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            box = get_box(conn, box_id)
            if not box:
                return "notfound", None
            if list_box_allocations(conn, box_id):
                return "allocated", None
            del_snap.update(box_id=box_id, place_id=box.get("place_id"), box_code=box.get("box_code"),
                            product_code=box.get("product_code"), quantity=box.get("quantity"))
            src = box.get("source_thread_id")
            box_code = box.get("box_code")
            # Phiếu ĐÓNG GÓI: hoàn nguyên liệu đã trừ tương ứng thùng này (ratio × số
            # cây thùng, kẹp theo tổng đã tiêu của phiếu) — allocation NL gắn PHIẾU chứ
            # không gắn thùng, nên phải hoàn theo tỉ lệ công thức lúc xoá từng thùng.
            restored = []
            if src:
                slip = get_slip(conn, src)
                if slip and (slip.get("kind") or "san_xuat") == "dong_goi":
                    from inventory_store import release_production_amount
                    for nd in recipe_needs(conn, box.get("product_code"), box.get("quantity") or 0):
                        got, into = release_production_amount(conn, src, nd["code"], nd["amount"])
                        if got > 0:
                            restored.append({"code": nd["code"], "amount": round(got, 3), "boxes": into})
            delete_box(conn, box_id)
            # Gỡ entry numbers của thùng khỏi phiếu SX nguồn → total tính lại đúng
            # (numbers là nguồn thật; note nhập lúc tạo = '📦 <box_code>'). Số gọi
            # tái dùng toàn kho nhưng TRONG 1 phiếu không thể trùng (<999 thùng/phiếu)
            # nên match theo note trong phạm vi phiếu vẫn an toàn.
            if src and box_code:
                remove_number_by_note(conn, src, f"📦 {box_code}")
            return "ok", (src, restored)
        finally:
            conn.close()
    status, res = await asyncio.to_thread(_run)
    if status == "notfound":
        return web.json_response({"ok": False, "error": "Không tìm thấy thùng"}, status=404)
    if status == "allocated":
        return web.json_response({"ok": False, "error": "Thùng đã xuất cho đơn — thu hồi khỏi đơn trước khi xoá"}, status=400)
    src, restored = res or (None, [])
    from server_app.realtime import emit_inventory_changed, emit_box_changed, emit_production_changed
    emit_inventory_changed()
    emit_box_changed()
    if src:
        emit_production_changed(src)
    # Lịch sử VỊ TRÍ: thùng bị admin xoá khỏi kho (lịch sử thùng: middleware DELETE)
    if del_snap.get("place_id"):
        from server_app.inventory_audit import log_box_deleted
        log_box_deleted(del_snap, actor=request.get("web_user") or request.remote,
                        actor_type="web_user" if request.get("web_user") else "http_client")
    return web.json_response({"ok": True, "restored_materials": restored})


async def box_return_material_handler(request: web.Request):
    """POST /api/inventory/box/{box_id}/return-material — RÃ 1 thùng nguyên kiện
    (KDXDB5/KGL5…) → hoàn lại TOÀN BỘ nguyên liệu theo công thức (ratio × số). Vô hiệu
    thùng (GIỮ lịch sử, không xoá). Hoàn NL = đảo tiêu hao của phiếu đóng gói nguồn
    (release_production_amount, trả về đúng thùng NL cũ); nguồn cũ thiếu bao nhiêu thì
    TẠO thùng NL mới bù cho đủ → đảm bảo luôn trả đủ. CHỈ admin."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được trả về nguyên liệu"}, status=403)
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    actor = _web_actor(request, {})

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            box = get_box(conn, box_id)
            if not box:
                return "notfound", None
            if box.get("disabled"):
                return "disabled", None
            if list_box_allocations(conn, box_id):   # đã xuất/đặt cho đơn → thu hồi trước
                return "allocated", None
            from product_store import get_product
            prod = get_product(conn, box.get("product_code"))
            if not prod or not prod.get("self_container"):
                return "notselfcont", None
            needs = recipe_needs(conn, box.get("product_code"), box.get("quantity") or 0)
            if not needs:
                return "norecipe", None
            src = box.get("source_thread_id")
            slip = get_slip(conn, src) if src else None
            src_pack = bool(slip and (slip.get("kind") or "san_xuat") == "dong_goi")
            from inventory_store import release_production_amount
            restored = []
            for nd in needs:
                got, into = (release_production_amount(conn, src, nd["code"], nd["amount"])
                             if src_pack else (0.0, []))
                short = round(nd["amount"] - got, 6)
                if short > 1e-6:   # nguồn cũ không đủ → tạo thùng NL mới bù cho đủ
                    fresh = add_boxes(conn, nd["code"], [short], by=actor,
                                      note=f"trả về từ thùng {box.get('box_code')}")
                    into = list(into) + [{"box_id": f["id"], "box_code": f["box_code"],
                                          "amount": short, "fresh": True} for f in fresh]
                    got += short
                if got > 1e-9:
                    restored.append({"code": nd["code"], "amount": round(got, 3), "boxes": into})
            mats = ", ".join(f"{r['amount']:g} {r['code']}" for r in restored) or "—"
            set_disabled(conn, box_id, True, f"Đã trả về nguyên liệu: {mats}")
            if src and box.get("box_code"):   # gỡ khỏi output phiếu nguồn (total tính lại)
                remove_number_by_note(conn, src, f"📦 {box.get('box_code')}")
            return "ok", (src, restored)
        finally:
            conn.close()
    status, res = await asyncio.to_thread(_run)
    _errs = {"notfound": ("Không tìm thấy thùng", 404), "disabled": ("Thùng đã vô hiệu", 400),
             "allocated": ("Thùng đã xuất cho đơn — thu hồi khỏi đơn trước", 400),
             "notselfcont": ("Chỉ áp dụng cho SP nguyên kiện (bán theo thùng)", 400),
             "norecipe": ("SP chưa có công thức nguyên liệu để trả về", 400)}
    if status in _errs:
        msg, code = _errs[status]
        return web.json_response({"ok": False, "error": msg}, status=code)
    src, restored = res or (None, [])
    from server_app.realtime import emit_inventory_changed, emit_box_changed, emit_production_changed
    emit_inventory_changed()
    emit_box_changed(box_id)
    if src:
        emit_production_changed(src)
    return web.json_response({"ok": True, "restored_materials": restored})


async def box_transfer_handler(request: web.Request):
    """POST /api/inventory/box/{box_id}/transfer — chuyển hàng sang thùng khác CÙNG SP.
    Body {to_box_id, quantity}. Bút toán kép box_allocations (transfer_out/+q trên
    nguồn, transfer_in/−q trên đích, cùng transaction) — tổng tồn bảo toàn, quantity
    gốc 2 thùng không đổi. Xem inventory_store.transfer_between_boxes."""
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _web_actor(request, body)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            from inventory_store import transfer_between_boxes
            return transfer_between_boxes(conn, box_id, body.get("to_box_id"), body.get("quantity"), by=actor)
        finally:
            conn.close()
    res, terr = await asyncio.to_thread(_run)
    if terr:
        return web.json_response({"ok": False, "error": terr}, status=400)
    actor_type = "web_user" if request.get("web_user") else "http_client"
    from server_app.realtime import emit_box_changed, emit_inventory_changed
    emit_box_changed(res["from_id"])
    emit_box_changed(res["to_id"])
    emit_inventory_changed()

    # Lịch sử THÙNG (cả 2) + VỊ TRÍ (nếu có xếp) — 1 nguồn duy nhất log_transfer_places,
    # payload giàu (mã+số thùng đối tác, tên kho, tồn) để timeline/History hiện đủ.
    def _places():
        conn = _conn()
        try:
            from server_app.inventory_audit import box_snapshot
            return box_snapshot(conn, res["from_id"]), box_snapshot(conn, res["to_id"])
        finally:
            conn.close()
    fs, ts = await asyncio.to_thread(_places)
    if fs and ts:
        from server_app.inventory_audit import log_transfer_places
        log_transfer_places(fs, ts, res["quantity"], actor=actor, actor_type=actor_type)
    return web.json_response({"ok": True, "transfer": res})


async def box_detail_handler(request: web.Request):
    """Chi tiết 1 thùng: info + phiếu SX nguồn (sp_name, ngày) + đơn đã xuất (nếu có)."""
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            box = get_box(conn, box_id)
            if not box:
                return None, None, None, None
            from product_store.queries import is_self_container_unit
            box["self_container"] = is_self_container_unit(box.get("product_unit"))
            allocs = list_box_allocations(conn, box_id)
            for a in allocs:
                kind = a.get("kind") or "order"
                if kind in ("transfer_out", "transfer_in"):
                    # order_thread_id = id thùng đối tác → gắn mã gọi để UI hiện đẹp
                    peer = get_box(conn, a.get("order_thread_id"))
                    a["peer_box_code"] = (peer or {}).get("box_code")
                else:
                    a["order_text"] = _order_first_line(conn, a.get("order_thread_id"))
            slip = get_slip(conn, box["source_thread_id"]) if box.get("source_thread_id") else None
            src_purchase = None
            if box.get("source_purchase_id"):
                # thùng tạo từ phiếu NHẬP HÀNG → link nguồn về #/nhap-hang/:id
                from purchase_store import get_purchase_full
                pu = get_purchase_full(conn, int(box["source_purchase_id"]))
                if pu:
                    src_purchase = {"id": pu["id"], "supplier_name": pu.get("supplier_name"),
                                    "created_at": pu.get("created_at")}
            # Thùng của phiếu ĐÓNG GÓI: liệt kê NL đã tiêu cho thùng này (ratio × số cây)
            # → client hiện popup xoá "đóng gói từ …, xoá sẽ hoàn NL".
            packed = []
            if slip and (slip.get("kind") or "san_xuat") == "dong_goi":
                packed = recipe_needs(conn, box.get("product_code"), box.get("quantity") or 0)
            return box, slip, allocs, packed, src_purchase
        finally:
            conn.close()
    box, slip, allocs, packed, src_purchase = await asyncio.to_thread(_run)
    if not box:
        return web.json_response({"ok": False, "error": "Không tìm thấy thùng"}, status=404)
    used = sum(a.get("quantity") or 0 for a in allocs)
    box["allocated"] = used
    box["remaining"] = float(box.get("quantity") or 0) - used
    source = None
    if slip:
        source = {"thread_id": slip["thread_id"], "date": slip.get("date"), "sp_name": slip.get("sp_name")}
    return web.json_response({"ok": True, "box": box, "source_slip": source, "allocations": allocs,
                              "source_purchase": src_purchase, "packed_materials": packed})


async def box_update_handler(request: web.Request):
    """Sửa ghi chú (và/hoặc số cây) của 1 thùng. Trả box sau khi cập nhật."""
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    note = body.get("note")
    quantity = body.get("quantity")
    mfg_date = body.get("mfg_date")
    kwargs = {}
    if note is not None:
        kwargs["note"] = str(note)
    if mfg_date is not None:
        kwargs["mfg_date"] = str(mfg_date).strip()
    if "place_id" in body:                       # đặt/gỡ vị trí kho
        pid = body.get("place_id")
        if pid is None or pid == "":
            kwargs["clear_place"] = True
        else:
            try:
                kwargs["place_id"] = int(pid)
            except (TypeError, ValueError):
                return web.json_response({"ok": False, "error": "place_id không hợp lệ"}, status=400)
    if body.get("unit_id"):                       # đổi đơn vị chứa
        try:
            kwargs["unit_id"] = int(body["unit_id"])
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "unit_id không hợp lệ"}, status=400)
    if quantity is not None:
        # ⛔ TẮT sửa số cây trực tiếp (2026-07-08): hàng chỉ 2 đường — nhập từ phiếu
        # SX, xuất bằng đơn. Sửa tay = lỗ hổng thất thoát (UI cũng không có nút này).
        return web.json_response(
            {"ok": False, "error": "Không sửa được số lượng thùng — hàng chỉ nhập từ phiếu SX và xuất bằng đơn"},
            status=400)
    if not kwargs:
        return web.json_response({"ok": False, "error": "Không có gì để sửa"}, status=400)
    actor = _web_actor(request, body)
    move: dict = {}   # CHUYỂN KHO → ghi lịch sử vị trí (cũ + mới)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            box = get_box(conn, box_id)
            if not box:
                return None, None
            # ⛔ Thùng ĐÃ XUẤT HẾT (remaining ≤ 0) = read-only: chỉ trao đổi (bình
            # luận/ảnh) được, cấm sửa ghi chú/ngày SX/đơn vị/CHUYỂN KHO (place_id).
            used = sum((a.get("quantity") or 0) for a in list_box_allocations(conn, box_id))
            if float(box.get("quantity") or 0) - used <= 1e-9:
                return None, "locked"
            update_box(conn, box_id, **kwargs)
            after = get_box(conn, box_id)
            if ("place_id" in kwargs or kwargs.get("clear_place")) and after and \
               (box.get("place_id") or None) != (after.get("place_id") or None):
                from server_app.inventory_audit import box_snapshot
                move.update(from_place_id=box.get("place_id"), from_name=box.get("place_name"),
                            to_place_id=after.get("place_id"), to_name=after.get("place_name"),
                            snap=box_snapshot(conn, box_id))   # có remaining cho timeline
            return after, None
        finally:
            conn.close()
    box, err = await asyncio.to_thread(_run)
    if err == "locked":
        return web.json_response(
            {"ok": False, "error": "Thùng đã xuất hết — chỉ trao đổi được, không sửa/chuyển kho"},
            status=400)
    if not box:
        return web.json_response({"ok": False, "error": "Không tìm thấy thùng"}, status=404)
    from server_app.realtime import emit_box_changed, emit_inventory_changed
    emit_box_changed(box_id)
    emit_inventory_changed()
    if move:   # lịch sử VỊ TRÍ: thùng rời kho cũ + đến kho mới (lịch sử thùng: middleware)
        from server_app.inventory_audit import log_box_moved
        log_box_moved(move["snap"], from_place_id=move["from_place_id"], from_name=move["from_name"],
                      to_place_id=move["to_place_id"], to_name=move["to_name"], actor=actor,
                      actor_type="web_user" if request.get("web_user") else "http_client")
    return web.json_response({"ok": True, "box": box})


async def bulk_move_handler(request: web.Request):
    """CHUYỂN KHO HÀNG LOẠT: đổi vị trí nhiều thùng sang 1 kho đích (POST /api/inventory/bulk-move,
    body {box_ids:[...], to_place_id}). Bỏ qua thùng không thấy / đã xuất hết / vô hiệu / đã ở
    kho đích. Cùng logic + audit (moved_out/in) + realtime như chuyển 1 thùng."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        box_ids = [int(x) for x in (body.get("box_ids") or [])]
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "box_ids không hợp lệ"}, status=400)
    if not box_ids:
        return web.json_response({"ok": False, "error": "Chưa chọn thùng"}, status=400)
    pid = body.get("to_place_id")
    try:
        to_place_id = int(pid)
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "Chưa chọn kho đích"}, status=400)
    actor = _web_actor(request, body)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            place = conn.execute("SELECT name FROM inventory_places WHERE id = ?", (to_place_id,)).fetchone()
            if not place:
                return None, None
            to_name = place[0]
            from server_app.inventory_audit import box_snapshot
            moves = []
            for bid in box_ids:
                box = get_box(conn, bid)
                if not box or box.get("disabled"):
                    continue
                used = sum((a.get("quantity") or 0) for a in list_box_allocations(conn, bid))
                if float(box.get("quantity") or 0) - used <= 1e-9:      # đã xuất hết → không chuyển
                    continue
                if (box.get("place_id") or None) == to_place_id:        # đã ở kho đích
                    continue
                update_box(conn, bid, place_id=to_place_id)
                moves.append({"box_id": bid, "from_place_id": box.get("place_id"),
                              "from_name": box.get("place_name"), "snap": box_snapshot(conn, bid)})
            return moves, to_name
        finally:
            conn.close()

    result, to_name = await asyncio.to_thread(_run)
    if result is None:
        return web.json_response({"ok": False, "error": "Không tìm thấy kho đích"}, status=404)
    from server_app.inventory_audit import log_box_moved
    from server_app.realtime import emit_box_changed, emit_inventory_changed
    at = "web_user" if request.get("web_user") else "http_client"
    for m in result:
        log_box_moved(m["snap"], from_place_id=m["from_place_id"], from_name=m["from_name"],
                      to_place_id=to_place_id, to_name=to_name, actor=actor, actor_type=at)
        emit_box_changed(m["box_id"])
    if result:
        emit_inventory_changed()
    return web.json_response({"ok": True, "moved": len(result), "skipped": len(box_ids) - len(result), "to_name": to_name})


async def box_disable_handler(request: web.Request):
    """Vô hiệu / kích hoạt lại 1 thùng. Vô hiệu = không tính tồn, không phân bổ đơn,
    trừ khỏi tổng phiếu SX nguồn (kích hoạt lại thì cộng vào). Vẫn hiển thị.

    ⛔ TẠM TẮT chiều VÔ HIỆU (2026-07-08): hàng chỉ có 2 đường đi — nhập từ phiếu
    SX, xuất bằng đơn. Chỉ còn cho KÍCH HOẠT LẠI thùng đã vô hiệu từ trước."""
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    disabled = bool(body.get("disabled", True))
    reason = str(body.get("reason") or "").strip()
    if disabled:
        return web.json_response(
            {"ok": False, "error": "Tính năng vô hiệu thùng đã tắt — hàng chỉ nhập từ phiếu SX và xuất bằng đơn"},
            status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            box = get_box(conn, box_id)
            if not box:
                return None, None
            was = bool(box.get("disabled"))
            if was == disabled:
                return box, None  # không đổi
            # Cấm vô hiệu thùng đã xuất 1 phần cho đơn — thu hồi khỏi đơn trước
            if disabled and list_box_allocations(conn, box_id):
                return box, "Thùng đã phân bổ vào đơn — thu hồi khỏi đơn trước khi vô hiệu"
            set_disabled(conn, box_id, disabled, reason=reason)
            # Đồng bộ tổng phiếu SX nguồn: vô hiệu → trừ, kích hoạt → cộng
            src = box.get("source_thread_id")
            if src:
                slip = get_slip(conn, src)
                if slip:
                    qty = box.get("quantity") or 0
                    total = (slip.get("total") or 0) + (-qty if disabled else qty)
                    set_total(conn, src, max(0, total))
            return get_box(conn, box_id), None
        finally:
            conn.close()
    box, err = await asyncio.to_thread(_run)
    if err:
        return web.json_response({"ok": False, "error": err}, status=409)
    if not box:
        return web.json_response({"ok": False, "error": "Không tìm thấy thùng"}, status=404)
    from server_app.realtime import emit_box_changed, emit_inventory_changed, emit_production_changed
    src = box.get("source_thread_id")
    if src:
        emit_production_changed(src)
    emit_box_changed(box.get("id"))
    emit_inventory_changed()
    return web.json_response({"ok": True, "box": box})


async def inventory_detail_handler(request: web.Request):
    """Tồn 1 product: tổng + nhóm theo size (5 thùng 50, x thùng 70…) + list thùng."""
    code = _product_code(request)
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã sản phẩm"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            all_boxes = list_boxes(conn, product_code=code)
            # Liên kết KiotViet + tên danh mục — resolve nhận cả MÃ CŨ trong URL
            from product_store import resolve_code
            prod = resolve_code(conn, code)
        finally:
            conn.close()
        return all_boxes, prod
    all_boxes, prod = await asyncio.to_thread(_run)
    # khả dụng phân bổ = thùng còn hiệu lực + còn lại > 0 (giữ quantity gốc + remaining)
    avail = [b for b in all_boxes if not b.get("disabled") and b.get("remaining", 0) > 0]
    # tồn = tổng CÒN LẠI → gộp theo remaining
    summary = summarize([{**b, "quantity": b["remaining"]} for b in avail])
    product = None
    if prod:
        product = {
            "id": prod.get("id"),
            "code": prod["code"], "name": prod.get("name") or prod.get("kv_full_name") or "",
            "can_produce_directly": bool(prod.get("can_produce_directly")),
            "self_container": bool(prod.get("self_container")),
            "min_stock": float(prod.get("min_stock") or 0),
            "can_sell": bool(prod.get("can_sell", True)),
            "can_purchase": bool(prod.get("can_purchase", True)),
            "cost_price": prod.get("cost_price") or 0, "unit": prod.get("unit") or "cây",
            "kv_id": prod.get("kv_id"), "kv_full_name": prod.get("kv_full_name"),
            "kv_synced_at": prod.get("kv_synced_at"),
            "linked": bool(prod.get("kv_id")),
        }
    return web.json_response({
        # mã hiện hành (URL có thể mang MÃ CŨ — client tự cập nhật theo mã này)
        "ok": True, "product_code": (prod or {}).get("code") or code,
        "boxes": avail, "all_boxes": all_boxes,
        "product": product, **summary,
    })


async def product_orders_handler(request: web.Request):
    """Lazy-load: các ĐƠN có mã SP này (phân trang). GET ?offset=&limit=.
    Trả {orders, total, has_more}. Lọc: invoice[].sp == code (kể cả invoice_items cũ)."""
    code = _product_code(request)
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã sản phẩm"}, status=400)
    try:
        offset = max(0, int(request.query.get("offset", "0")))
        limit = max(1, min(50, int(request.query.get("limit", "20"))))
    except (ValueError, TypeError):
        offset, limit = 0, 20

    def _run():
        conn = _conn()
        try:
            from order_store.product_orders import orders_containing_product, count_orders_containing_product
            total = count_orders_containing_product(conn, code)
            orders = orders_containing_product(conn, code, limit=limit, offset=offset)
        finally:
            conn.close()
        return orders, total
    orders, total = await asyncio.to_thread(_run)
    return web.json_response({
        "ok": True, "product_code": code, "orders": orders, "total": total,
        "has_more": offset + len(orders) < total,
    })


# ─── xuất / thu thùng cho đơn ─────────────────────────────────────────────────
def _order_product_stock(conn, thread_id) -> dict:
    """{MÃ SP (hoa) trong hoá đơn: tồn hiện tại của kho}. Tồn = tổng CÒN LẠI của thùng
    còn hiệu lực; khớp theo product_id nên mã cũ (alias) vẫn ra đúng SP. 1 lượt
    product_summary (đã trừ mọi phân bổ, kể cả của đơn này = tồn thực còn lại)."""
    from product_store import resolve_code_to_id
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return {}
    codes: list[str] = []
    for it in (order.get("invoice") or []):
        c = str(it.get("sp") or "").strip().upper()
        if c and c not in codes:
            codes.append(c)
    if not codes:
        return {}
    summ = product_summary(conn)
    by_id = {s["product_id"]: (s.get("in_stock_total") or 0) for s in summ if s.get("product_id") is not None}
    by_code = {s["product_code"]: (s.get("in_stock_total") or 0) for s in summ}
    out: dict = {}
    for c in codes:
        pid = resolve_code_to_id(conn, c)
        out[c] = by_id.get(pid, by_code.get(c, 0)) if pid is not None else by_code.get(c, 0)
    return out


async def order_allocations_handler(request: web.Request):
    """Các phần thùng đã xuất cho đơn này (1 dòng = 1 phần thùng) + tồn hiện tại của
    từng mã SP trong đơn (để trang xuất kho hiện tồn kho từng SP)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return list_order_allocations(conn, thread_id), _order_product_stock(conn, thread_id)
        finally:
            conn.close()
    allocs, stock = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "allocations": allocs, "stock": stock})


async def order_allocate_handler(request: web.Request):
    """Xuất kho cho đơn: picks=[{box_id, quantity?}] → ghi phần lấy (thùng KHÔNG tách).

    quantity thiếu = lấy hết phần còn lại của thùng.
    """
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    picks = body.get("picks")
    if not isinstance(picks, list) or not picks:
        box_ids = body.get("box_ids")
        if isinstance(box_ids, list) and box_ids:
            picks = [{"box_id": b, "quantity": None} for b in box_ids]
        else:
            return web.json_response({"ok": False, "error": "Chưa chọn thùng"}, status=400)
    actor = _web_actor(request, body)
    # Đơn đã CHỐT xuất kho → khoá (trừ admin)
    from server_app.order_stock_lock import stock_locked_error
    locked = await stock_locked_error(request, thread_id)
    if locked:
        return locked

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            allocated = allocate_picks(conn, picks, thread_id, by=actor)
            order_text = _order_first_line(conn, thread_id)
            from server_app.inventory_audit import box_snapshot
            aud = []
            for a in allocated:
                s = box_snapshot(conn, a.get("box_id"))
                if s:
                    s.update(order_thread_id=thread_id, order_text=order_text, taken=a.get("quantity"))
                    aud.append(s)
            return list_order_allocations(conn, thread_id), allocated, aud
        finally:
            conn.close()
    allocs, allocated, aud = await asyncio.to_thread(_run)
    from server_app.realtime import emit_box_changed, emit_inventory_changed, emit_order_changed
    emit_order_changed(thread_id)   # picking của đơn đổi → chi tiết đơn + OrderStock
    emit_inventory_changed()        # tồn kho đổi → trang Kho / thùng
    for pk in picks:
        try:
            emit_box_changed(int(pk.get("box_id")))
        except (TypeError, ValueError):
            pass
    # Lịch sử: xuất cho đơn (lịch sử THÙNG + lịch sử VỊ TRÍ)
    from server_app.inventory_audit import log_boxes_allocated
    log_boxes_allocated(aud, actor=actor,
                        actor_type="web_user" if request.get("web_user") else "http_client")
    return web.json_response({"ok": True, "allocated": allocated, "allocations": allocs})


async def order_release_handler(request: web.Request):
    """Thu hồi 1 phần thùng khỏi đơn (xoá allocation theo allocation_ids)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = body.get("allocation_ids")
    if not isinstance(ids, list) or not ids:
        return web.json_response({"ok": False, "error": "Chưa chọn phần thùng"}, status=400)
    actor = _web_actor(request, body)
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "allocation_ids không hợp lệ"}, status=400)
    # Đơn đã CHỐT xuất kho → khoá thu hồi (trừ admin)
    from server_app.order_stock_lock import stock_locked_error
    locked = await stock_locked_error(request, thread_id)
    if locked:
        return locked

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            from server_app.inventory_audit import box_snapshot
            order_text = _order_first_line(conn, thread_id)
            released = []
            aud = []
            for aid in ids:
                a = get_allocation(conn, aid)
                if a and a.get("order_thread_id") == thread_id:
                    s = box_snapshot(conn, a.get("box_id"))
                    delete_allocation(conn, aid)
                    if s:
                        # remaining SAU khi hoàn = trước (còn allocation) + phần vừa trả
                        s["remaining"] = (s.get("remaining") or 0) + float(a.get("quantity") or 0)
                        s.update(order_thread_id=thread_id, order_text=order_text, taken=a.get("quantity"))
                        aud.append(s)
                    released.append(aid)
            return list_order_allocations(conn, thread_id), released, aud
        finally:
            conn.close()
    allocs, released, aud = await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed, emit_order_changed
    emit_order_changed(thread_id)   # picking của đơn đổi
    emit_inventory_changed()        # tồn kho trả lại → trang Kho / thùng
    # Lịch sử: thu hồi về kho (lịch sử THÙNG + lịch sử VỊ TRÍ)
    from server_app.inventory_audit import log_boxes_released
    log_boxes_released(aud, actor=actor,
                       actor_type="web_user" if request.get("web_user") else "http_client")
    return web.json_response({"ok": True, "released": released, "allocations": allocs})
