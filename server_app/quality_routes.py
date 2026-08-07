"""HTTP BÁO CÁO CHẤT LƯỢNG MÂM KẸO — /api/quality (100% local).

GET list (dashboard: thợ nào đã/chưa chụp mâm hôm nay) · GET {worker_id} chi tiết
thợ + báo cáo · POST {worker_id}/report tạo báo cáo hôm nay (mọi user, ymd tính
SERVER) · POST report/{rid}/delete (admin) · POST settings chọn thợ hiện trên bảng
(văn phòng). Thợ lấy từ `production_workers` (worker_store) — trang này KHÔNG
tạo/sửa/xoá thợ, việc đó ở #/tho. Ảnh gắn báo cáo qua media scope 'quality_report'.
Nối: quality_store, worker_store, entity_media_store, settings_store,
server_app.realtime, audit_log. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

import quality_store
import worker_store
from entity_media_store import image_counts, latest_image_ids
from quality_store import domain
from server_app.photo_report_view import attach_today_scores, enrich_reports
from utils.db import get_connection

log = logging.getLogger("quality_routes")

# Chỉ VÀI thợ sửa kẹo → bảng #/chat-luong chỉ hiện những thợ được chọn, theo ĐÚNG
# thứ tự đã sắp (vị trí trong lưới 2 cột). Lưu 1 key trong settings_store
# (kv_store['app_settings']) = cấu hình CHUNG cả tiệm, mọi máy thấy giống nhau.
# [] hoặc thiếu key = CHƯA cấu hình → hiện TẤT CẢ thợ (hành vi cũ, không phá gì).
_BOARD_KEY = "quality_board_workers"


def _board_columns() -> list[list[int]]:
    """Cấu hình "thợ nào ở cột nào" — [[cột 1], [cột 2]]. Đọc được cả dạng cũ
    (danh sách phẳng) nên bản cũ đã lưu vẫn hiện đúng."""
    from settings_store import get_all
    return domain.clean_board_columns(get_all().get(_BOARD_KEY))


def _board_ids() -> list[int]:
    return domain.flatten_columns(_board_columns())


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _conn():
    conn = get_connection()
    quality_store.ensure_tables(conn)
    worker_store.ensure_table(conn)
    return conn


def _actor_type(request: web.Request) -> str:
    return "web_user" if request.get("web_user") else "http_client"


def _audit(action: str, worker_id, actor: str, actor_type: str, payload: dict) -> None:
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope="quality", thread_id=worker_id, actor_type=actor_type,
        actor_id=actor, source=action, payload=payload))


def _worker(conn, worker_id: int) -> dict | None:
    """1 thợ theo id (danh sách thợ nhỏ — lọc trong Python, khỏi thêm API store)."""
    for w in worker_store.list_workers(conn):
        if int(w["id"]) == int(worker_id):
            return w
    return None


# ── Dashboard ────────────────────────────────────────────────────────────────
async def quality_all_handler(request: web.Request):
    """GET /api/quality — dashboard: thợ + trạng thái chụp mâm hôm nay + dải 7 ngày."""
    def _run():
        conn = _conn()
        try:
            today = domain.today_vn()
            # ghi chú hồ sơ thợ là chuyện văn phòng → KHÔNG đẩy ra bảng chung
            workers = [{"id": w["id"], "name": w["name"], "note": ""}
                       for w in worker_store.list_workers(conn)]
            week_from = domain.last_n_days(today, 7)[0]
            reports = quality_store.list_reports_since(conn, week_from)
            # số ảnh mỗi báo cáo (để "reported" chỉ đúng khi ≥1 ảnh)
            counts = image_counts("quality_report", [int(r["id"]) for r in reports])
            for r in reports:
                r["photo_count"] = int(counts.get(int(r["id"]), 0))
            rows, done = domain.build_dashboard_rows(workers, reports, today, week=7)
            # điểm TB mâm hôm nay của từng thợ (chấm điểm 0–10 trên từng ảnh)
            attach_today_scores("quality_report", rows,
                                {int(r["worker_id"]): int(r["id"]) for r in reports
                                 if str(r.get("ymd")) == today})
            # thumbnail = ảnh mới nhất của BÁO CÁO GẦN NHẤT mỗi thợ (reports đã sort
            # mới→cũ nên id đầu tiên gặp = gần nhất).
            latest_map: dict[int, int] = {}
            for r in reports:
                latest_map.setdefault(int(r["worker_id"]), int(r["id"]))
            thumbs = latest_image_ids("quality_report", list(latest_map.values()))
            for row in rows:
                rid = latest_map.get(row["id"])
                img = thumbs.get(rid) if rid else None
                row["thumb_image_id"] = img
                # report_id chứa ảnh thumb (webapp dựng URL /api/media/quality_report/{rid})
                row["thumb_report_id"] = rid if img else None
            return today, rows, done, len(workers), _board_columns()
        finally:
            conn.close()
    today, rows, done, total, columns = await asyncio.to_thread(_run)
    # Trả CẢ danh sách thợ (popup cài đặt cần chọn từ đủ danh sách) + cấu hình cột;
    # webapp dựng lưới theo board_columns (mỗi cột một danh sách, đúng thứ tự).
    board = domain.flatten_columns(columns)
    shown = domain.select_board_rows(rows, board)
    done_shown = sum(1 for r in shown if r["today"].get("reported"))
    return web.json_response({"ok": True, "today_ymd": today, "workers": rows,
                              "board_columns": columns,
                              "board_worker_ids": board,          # giữ cho client cũ
                              "done_count": done_shown if board else done,
                              "total": len(shown) if board else total})


async def quality_worker_handler(request: web.Request):
    """GET /api/quality/{id} — thợ + báo cáo (mỗi báo cáo kèm images + photo_count)."""
    try:
        wid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    viewer = str(request.get("web_user") or "")   # điểm chấm RIÊNG mỗi người → cần biết ai xem

    def _get():
        conn = _conn()
        try:
            worker = _worker(conn, wid)
            if not worker:
                return None, None, None
            reports = quality_store.list_reports(conn, wid)
            # ảnh + điểm 0–10 (kèm điểm CỦA NGƯỜI ĐANG XEM) + số bình luận
            enrich_reports("quality_report", "quality_image", reports, viewer)
            return worker, reports, domain.today_vn()
        finally:
            conn.close()
    worker, reports, today = await asyncio.to_thread(_get)
    if not worker:
        return web.json_response({"ok": False, "error": "Không tìm thấy thợ"}, status=404)
    return web.json_response({
        "ok": True,
        "worker": {"id": worker["id"], "name": worker["name"]},
        "reports": reports, "today_ymd": today,
    })


# ── Báo cáo chất lượng ───────────────────────────────────────────────────────
async def quality_report_handler(request: web.Request):
    """POST /api/quality/{id}/report — MỌI user. ymd = hôm nay (tính SERVER). Idempotent
    theo ngày: đã có báo cáo hôm nay thì trả lại (created=false) để chụp thêm mâm."""
    try:
        wid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    note = str(body.get("note") or "").strip()
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            worker = _worker(conn, wid)
            if not worker:
                return None, None, None, None, "Không tìm thấy thợ"
            ymd = domain.today_vn()
            rep, created = quality_store.get_or_create_report(conn, wid, ymd, by=actor, note=note)
            return rep, created, ymd, worker, None
        finally:
            conn.close()
    rep, created, ymd, worker, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)

    from server_app.realtime import emit_quality_changed
    emit_quality_changed(wid)
    if created:
        _audit("quality.report_created", wid, actor, _actor_type(request),
               {"worker_id": wid, "worker_name": (worker or {}).get("name") or "",
                "report_id": rep["id"], "ymd": ymd})
    return web.json_response({"ok": True, "report_id": rep["id"], "ymd": ymd, "created": created})


async def quality_products_handler(request: web.Request):
    """GET /api/quality/products?search= — danh sách SẢN PHẨM để chọn khi chụp mâm.

    Cố ý đặt DƯỚI /api/quality thay vì dùng /api/products: vai trò `chat_luong` chỉ
    được phép gọi /api/quality* (web_auth/role_scope), nên endpoint riêng ở đây
    giữ nguyên nguyên tắc ít quyền nhất — khỏi mở cả kho sản phẩm cho vai trò đó.
    Chỉ trả code + name (không giá, không tồn)."""
    q = str(request.query.get("search", "")).strip()

    def _run():
        from product_store import get_all_products
        from vn import vn_normalize
        conn = get_connection()
        try:
            items = get_all_products(conn)
        finally:
            conn.close()
        nq = vn_normalize(q)
        if nq:
            items = [p for p in items
                     if nq in vn_normalize(p.get("code") or "")
                     or nq in vn_normalize(p.get("name") or "")]
        return [{"code": p["code"], "name": p.get("name") or ""} for p in items[:200]]
    try:
        out = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        log.warning("quality products lỗi: %s", e)
        return web.json_response({"ok": True, "products": []})
    return web.json_response({"ok": True, "products": out})


async def quality_gallery_handler(request: web.Request):
    """GET /api/quality/gallery?days=N — MỌI ảnh mâm kẹo gần đây, gom theo NGÀY rồi
    theo THỢ (mới nhất trước) cho trang xem tất cả hình. Kèm điểm từng ảnh (trung
    bình + điểm của người đang xem) như trang chi tiết."""
    try:
        days = max(1, min(int(request.query.get("days", 14)), 120))
    except (TypeError, ValueError):
        days = 14
    viewer = str(request.get("web_user") or "")

    def _run():
        conn = _conn()
        try:
            today = domain.today_vn()
            since = domain.last_n_days(today, days)[0]
            reports = quality_store.list_reports_since(conn, since)
            names = {int(w["id"]): w["name"] for w in worker_store.list_workers(conn)}
        finally:
            conn.close()
        enrich_reports("quality_report", "quality_image", reports, viewer)
        out = []
        for r in reports:                       # list_reports_since đã sắp mới→cũ
            if not r.get("images"):
                continue                        # báo cáo chưa có ảnh: không vào gallery
            wid = int(r["worker_id"])
            out.append({
                "report_id": int(r["id"]), "ymd": r["ymd"],
                "worker_id": wid, "worker_name": names.get(wid, f"thợ #{wid}"),
                "created_by": r.get("created_by") or "", "created_at": r.get("created_at") or "",
                "images": r["images"], "score_avg": r.get("score_avg"),
            })
        return today, out
    today, groups = await asyncio.to_thread(_run)
    total = sum(len(g["images"]) for g in groups)
    return web.json_response({"ok": True, "today_ymd": today, "days": days,
                              "groups": groups, "total_images": total})


async def quality_settings_handler(request: web.Request):
    """POST /api/quality/settings — chọn THỢ NÀO hiện trên bảng + THỨ TỰ (vị trí ô).
    Văn phòng (admin/van_phong) vì đây là cấu hình chung cả tiệm, không phải sở
    thích riêng máy. Body {worker_ids: [id,…]} — mảng RỖNG = hiện lại tất cả thợ."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response(
            {"ok": False, "error": "Chỉ văn phòng mới đổi được cài đặt bảng"}, status=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    # Dạng MỚI: {"columns": [[id…],[id…]]} = thợ nào ở CỘT nào, thứ tự trong cột.
    # Vẫn nhận {"worker_ids": [...]} của client cũ (rải đều trái→phải).
    raw = body.get("columns") if isinstance(body.get("columns"), list) else body.get("worker_ids")
    if not isinstance(raw, list):
        return web.json_response(
            {"ok": False, "error": "cần 'columns' (mảng các cột) hoặc 'worker_ids' (mảng)"}, status=400)
    payload = {"columns": raw} if isinstance(body.get("columns"), list) else raw
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            valid = {int(w["id"]) for w in worker_store.list_workers(conn)}
        finally:
            conn.close()
        cols = domain.clean_board_columns(payload, valid)   # bỏ thợ đã xoá + trùng, GIỮ thứ tự
        from settings_store import set_value
        set_value(_BOARD_KEY, {"columns": cols})
        return cols
    cols = await asyncio.to_thread(_save)
    ids = domain.flatten_columns(cols)

    from server_app.realtime import emit_quality_changed
    emit_quality_changed(None)                # mọi máy đang mở bảng tự tải lại
    _audit("quality.board_settings", None, actor, _actor_type(request),
           {"columns": cols, "count": len(ids)})
    return web.json_response({"ok": True, "board_columns": cols, "board_worker_ids": ids})


async def quality_report_delete_handler(request: web.Request):
    """POST /api/quality/report/{rid}/delete — CHỈ admin, xoá mềm báo cáo."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá báo cáo"}, status=403)
    try:
        rid = int(request.match_info.get("rid", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _del():
        conn = _conn()
        try:
            rep = quality_store.get_report(conn, rid)
            worker = _worker(conn, int(rep["worker_id"])) if rep else None
            ok, err = quality_store.soft_delete_report(conn, rid, by=actor)
            return rep, worker, ok, err
        finally:
            conn.close()
    rep, worker, ok, err = await asyncio.to_thread(_del)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)

    worker_id = int(rep["worker_id"]) if rep else None
    from server_app.realtime import emit_quality_changed
    emit_quality_changed(worker_id)
    _audit("quality.report_deleted", worker_id, actor, _actor_type(request),
           {"worker_id": worker_id, "worker_name": (worker or {}).get("name") or "",
            "report_id": rid, "ymd": (rep or {}).get("ymd")})
    return web.json_response({"ok": True})
