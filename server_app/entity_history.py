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

_ACTION_LABELS = {"order.created": "Tạo đơn", "production.created": "Tạo phiếu SX", "box.created": "Tạo thùng"}

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
}
_SKIP = {"POST /api/production/{id}/report/parse"}   # xem trước, không phải ghi


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
        out: list[dict] = []
        for r in rows:
            act = r["action"]
            if act in _ACTION_LABELS:
                out.append({"ts": r["ts"], "actor": _actor_display(r["actor_id"], names),
                            "action": _ACTION_LABELS[act], "detail": "", "changes": [], "ok": True})
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
                try:
                    b = json.loads(r["payload_json"] or "{}").get("body")
                    if isinstance(b, str) and b.strip().startswith("{"):
                        bd = json.loads(b)
                        if is_report:
                            detail = _report_detail(str(bd.get("text") or ""))
                        elif key == "POST /api/inventory/box/{id}":
                            la = _box_update_action(bd, places)
                            if la:
                                label_override, detail = la
                        else:
                            detail = str(bd.get("text") or bd.get("note") or "")[:50]
                except Exception:
                    detail = ""
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
                            "action": label_override or _label(key, method, path), "detail": detail, "changes": [],
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
    if scope not in ("production", "box"):
        return web.json_response({"ok": False, "error": "scope không hợp lệ"}, status=400)
    try:
        entity_id = int(request.match_info.get("entity_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "entity_id không hợp lệ"}, status=400)
    history = await asyncio.to_thread(get_entity_history, scope, entity_id)
    return web.json_response({"ok": True, "history": history})
