"""Dịch 1 audit row → dòng feed Lịch sử thao tác toàn cục (#/lich-su).

Phủ MỌI scope + MỌI domain event (trước chỉ đơn/SX/thùng). Nhãn + parts lấy từ
server_app/event_format (event) và order_history/entity_history (request). Khử
trùng lặp: request có event nghiệp vụ tương ứng (±15s) → bỏ dòng request, giữ
event (chi tiết hơn); event nhân bản box↔place giữ 1 bản. Nối: server_app/activity.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from server_app.event_format import event_entry
from server_app.entity_history import (
    _ACTION_LABELS, _SKIP, _box_update_action, _customer_update_action,
    _label as _ent_label, _norm as _ent_norm, _place_update_action,
    _report_detail, _task_update_action,
)
from server_app.history_format import href_for, money, part, parts_text, product_href
from server_app.order_history import _LABELS as _ORDER_LABELS, _detail as _order_detail, _norm as _order_norm

_ORDER_ID = re.compile(r"/api/order/(-?\d+)")
_PROD_CODE = re.compile(r"^/api/products/([^/]+)")

_SCOPE_LABEL = {"order": "Đơn", "production": "Phiếu SX", "box": "Thùng", "place": "Vị trí",
                "customer": "Khách", "task": "Việc", "return": "Trả hàng", "disposal": "Xuất hủy",
                "purchase": "Nhập hàng", "supplier": "NCC", "product": "Sản phẩm", "unit": "Đơn vị",
                "worker": "Thợ", "price": "Bảng giá", "quy": "Quỹ", "stocktake": "Kiểm kho",
                "report_slip": "Báo cáo SX", "settings": "Cài đặt", "user": "User", "app": "Hệ thống"}

# event → scope hiển thị khi row.scope trống (event cũ ghi thiếu scope)
_EVENT_SCOPE = {"order": "order", "box": "box", "production": "production", "return": "return",
                "purchase": "purchase", "supplier": "supplier", "product": "product",
                "quy": "quy", "disposal": "disposal", "stocktake": "place", "settings": "settings",
                "customer": "customer"}

# Event nhân bản: box.* ghi cho CẢ thùng lẫn vị trí → feed giữ 1 bản (scope box);
# moved_in/out là bản phụ của box.moved; allocated/released đã có bản gộp theo ĐƠN.
_SKIP_PLACE_COPY = {"box.created", "box.allocated", "box.released", "box.consumed",
                    "box.transfer_out", "box.transfer_in", "box.disposed", "box.disposal_released",
                    "box.purchase_in", "box.purchase_in_removed", "box.return_in",
                    "adjustment.created", "adjustment.deleted"}
_SKIP_EVENTS = {"box.moved_out", "box.moved_in"}
_SKIP_BOX_COPY = {"box.allocated", "box.released"}   # bản gộp = order.stock_*

# request ↔ event nghiệp vụ: thấy event tương ứng (±15s, cùng entity nếu biết)
# → bỏ dòng request (event chi tiết hơn). Tạo đơn chờ mở topic Telegram lâu → 120s.
_PAIR_WINDOW = {"POST /api/order/create": 120.0}
_PAIRS = {
    "POST /api/order/create": ("order.created",),
    "POST /api/order/{id}/images": ("order.image_added",),
    "DELETE /api/order/{id}/images/{id}": ("order.image_deleted",),
    "POST /api/order/{id}/allocate": ("order.stock_allocated",),
    "POST /api/order/{id}/release": ("order.stock_released",),
    "POST /api/order/{id}/stock-confirm": ("order.stock_confirmed", "order.stock_unconfirmed"),
    "POST /api/order/payment/bulk": ("order.bulk_payment",),
    "POST /api/production": ("production.created",),
    "POST /api/production/{id}/boxes": ("box.created",),
    "DELETE /api/inventory/box/{id}": ("box.deleted",),
    "POST /api/returns": ("return.created",),
    "POST /api/customers/{id}/returns": ("return.created",),
    "POST /api/disposals": ("disposal.created",),
    "POST /api/disposals/{id}/delete": ("disposal.deleted",),
    "POST /api/purchases": ("purchase.created",),
    "POST /api/purchases/{id}/pay": ("purchase.paid",),
    "POST /api/purchases/{id}/receive-goods": ("purchase.goods_line_added",),
    "POST /api/purchases/{id}/confirm-goods": ("purchase.goods_received",),
    "POST /api/purchases/{id}/unreceive": ("purchase.goods_line_removed",),
    "POST /api/purchases/{id}/undo-goods": ("purchase.goods_undone",),
    "POST /api/purchases/{id}/payments/{id}/delete": ("purchase.payment_deleted",),
    "POST /api/suppliers": ("supplier.created",),
    "POST /api/quy": ("quy.created",),
    "DELETE /api/quy/{id}": ("quy.deleted",),
    "POST /api/places/{id}/stocktakes": ("stocktake.created",),
    "POST /api/stocktakes/{id}/complete": ("stocktake.completed",),
    "POST /api/stocktakes/{id}/apply": ("stocktake.applied",),
    "POST /api/inventory/box/{id}/adjust": ("adjustment.created",),
    "POST /api/adjustments/{id}/delete": ("adjustment.deleted",),
    "POST /api/settings": ("settings.changed",),
    "POST /api/quy-cach": ("settings.quy_cach_changed",),
    "POST /api/products": ("product.created",),
    # SP theo MÃ (path không phải số — chuẩn hoá {code} riêng)
    "POST /api/products/{code}": ("product.updated",),
    "POST /api/products/{code}/rename": ("product.renamed",),
    "DELETE /api/products/{code}": ("product.deleted",),
    "POST /api/products/{code}/link": ("product.linked",),
    "POST /api/products/{code}/unlink": ("product.unlinked",),
    "POST /api/products/{code}/kiotviet-create": ("product.linked", "product.created"),
}

# endpoint SP theo mã KHÔNG có event riêng → nhãn + link SP
_PRODUCT_LABELS = {
    "POST /api/products/{code}/recipe": "Sửa công thức sản xuất",
    "DELETE /api/products/{code}/recipe/{id}": "Xoá nguyên liệu khỏi công thức",
    "POST /api/products/{code}/kiotviet-create": "Tạo SP trên KiotViet",
}
_PRODUCT_PATH = re.compile(r"^/api/products/([^/]+)")
_USERS_PATH = re.compile(r"^(/api/users/)[^/]+(/)")

# path (chuẩn hoá {id}) → nhãn cho endpoint scope=None / chưa có nhãn đẹp
_EXTRA_LABELS = {
    "POST /api/customers/new": "Tạo khách hàng",
    "POST /api/customers/{id}/refresh-debt": None,   # đọc nợ KV — không phải thao tác
    "POST /api/customer/price": None,                # tra giá — read-only
    "POST /api/order/refresh-debt": None,
    "POST /api/reminder/stop/{id}": "Tắt nhắc nộp tiền",
    "POST /api/places": "Tạo vị trí kho",
    "POST /api/customers/{id}/link-kiotviet": "Liên kết khách với KiotViet",
    "POST /api/customers/{id}/unlink-kiotviet": "Gỡ liên kết KiotViet",
    "POST /api/price-lists": "Tạo bảng giá",
    "POST /api/units": "Tạo đơn vị chứa",
    "POST /api/units/{id}": "Sửa đơn vị chứa",
    "POST /api/workers": "Thêm thợ",
    "POST /api/workers/reorder": "Sắp xếp thứ tự thợ",
    "POST /api/wages": "Sửa bảng lương SP",
    "POST /api/attendance/map": "Gán ID chấm công cho thợ",
    "POST /api/attendance/manual": "Thêm giờ chấm công (sửa tay)",
    "POST /api/attendance/manual/delete": "Xoá giờ chấm tay",
    "POST /api/attendance/suppress": "Ẩn/hiện giờ chấm máy",
    "POST /api/report-slips": "Tạo phiếu báo cáo SX",
    "POST /api/report-slips/{id}": "Sửa phiếu báo cáo SX",
    "DELETE /api/report-slips/{id}": "Xoá phiếu báo cáo SX",
    "POST /api/tasks": "Tạo việc",
    "POST /api/cashbox/transfer": "Chuyển tiền giữa két",
    "POST /api/cashbox/withdraw": "Thu hồi tiền két",
    "POST /api/cashbox/transfer/{id}/delete": "Xoá lần chuyển tiền két",
    "POST /api/banner/pin": "Ghim lên bảng tin",
    "DELETE /api/banner/pin/{id}": "Bỏ ghim bảng tin",
    "POST /api/users": "Tạo tài khoản",
    "POST /api/users/{id}/role": "Đổi quyền tài khoản",
    "POST /api/users/{id}/disabled": "Khoá/mở tài khoản",
    "POST /api/users/{id}/pin": "Đặt lại PIN",
    "POST /api/app/reload": "Ép tải lại webapp mọi máy",
    "POST /api/inventory/bulk-move": "Chuyển kho hàng loạt",
    "POST /api/inventory/box/{id}/return-material": "Trả thùng về nguyên liệu",
    "POST /api/inventory/box/{id}/disable": "Vô hiệu / kích hoạt thùng",
    "POST /api/stocktakes/{id}": "Lưu đếm kiểm kho",
    "POST /api/places/{id}/stocktakes": "Tạo phiếu kiểm kho",   # fallback khi event rớt cặp
    "POST /api/auth/login": None, "POST /api/usage/batch": None,
    "POST /api/tg/edit-message": None, "POST /api/tg/send-message": None, "POST /api/tg/send-file": None,
}
_NOISE = {"/api/order/preview", "/api/order/totals", "/api/order/refresh-view"}
_WRITE = ("POST ", "DELETE ", "PUT ", "PATCH ")


def epoch(value) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0


def _scope_of_path(path: str) -> str | None:
    """Suy scope cho request scope=None từ path (để gắn nhãn nhóm + href)."""
    for pref, sc in (("/api/customers", "customer"), ("/api/price-lists", "price"),
                     ("/api/units", "unit"), ("/api/workers", "worker"), ("/api/wages", "production"),
                     ("/api/report-slips", "report_slip"), ("/api/tasks", "task"),
                     ("/api/users", "user"), ("/api/app/", "app"), ("/api/quy-cach", "settings"),
                     ("/api/settings", "settings"),
                     ("/api/stocktakes", "stocktake"), ("/api/inventory", "box"), ("/api/banner", "app"),
                     ("/api/quy", "quy"), ("/api/reminder", "order")):
        if path.startswith(pref):
            return sc
    return None


def _body(payload_json) -> dict:
    try:
        b = json.loads(payload_json or "{}").get("body")
        if isinstance(b, str) and b.strip().startswith("{"):
            return json.loads(b)
    except Exception:
        pass
    return {}


def event_row(r, resolver) -> dict | None:
    """Row domain-event → meta feed {scope, eid, label, parts} | None nếu bỏ."""
    act = r["action"]
    if act in _SKIP_EVENTS or act in _SKIP_BOX_COPY:
        return None
    scope = r["scope"] or _EVENT_SCOPE.get(act.split(".", 1)[0])
    if scope == "place" and act in _SKIP_PLACE_COPY:
        return None   # bản box đã hiện
    try:
        pl = json.loads(r["payload_json"] or "{}")
        pl = pl if isinstance(pl, dict) else {}
    except Exception:
        pl = {}
    ent = event_entry(act, pl, resolver)
    if ent:
        label, parts = ent
        if not parts and pl.get("detail"):
            parts = [part(str(pl["detail"])[:80])]
    elif act in _ACTION_LABELS:
        label, parts = _ACTION_LABELS[act], []
    else:
        return None   # event lạ/kỹ thuật — không thuộc feed
    eid = r["thread_id"]
    href = href_for(scope, eid) if scope else ""
    if scope == "product":   # trang SP theo MÃ, event mang code trong payload
        code = pl.get("code") or pl.get("new_code") or (resolver.product_code_by_id(eid) if resolver else None)
        href = product_href(code)
    if act == "settings.changed":
        href = "#/login"   # trang Cài đặt
    return {"scope": scope or "app", "eid": eid, "label": label, "parts": parts,
            "href": href, "image_id": pl.get("image_id")}


def _status_of(r):
    try:
        return json.loads(r["result_json"] or "{}").get("status")
    except Exception:
        return None


def http_row(r, resolver, event_times) -> dict | None:
    """Row http.request (ghi) → meta feed | None nếu bỏ (đọc/nhiễu/đã có event)."""
    source = r["source"] or ""
    if not source.startswith(_WRITE):
        return None
    raw_path = source.split(" ", 1)[1].split("?")[0]
    if raw_path in _NOISE:
        return None
    method, key, path = _ent_norm(source)
    if key in _SKIP:
        return None
    # path SP theo MÃ / user theo TÊN → chuẩn hoá thêm ({code}/{id})
    prod_code = None
    m = _PRODUCT_PATH.match(path)
    if m and m.group(1) != "{id}":
        prod_code = m.group(1)
        key = f"{method} " + _PRODUCT_PATH.sub("/api/products/{code}", path)
    key = re.sub(r"^(\w+) /api/users/[^/]+/", r"\1 /api/users/{id}/", key)
    key = re.sub(r"^(\w+) /api/customers/[^/]+/", r"\1 /api/customers/{id}/", key)
    # đã có event nghiệp vụ chi tiết hơn (cùng entity nếu biết, trong cửa sổ) → bỏ
    # dòng request. Request LỖI (4xx/5xx) không bỏ — event của nó không tồn tại.
    paired = _PAIRS.get(key)
    status = _status_of(r)
    ok2xx = status is None or (isinstance(status, int) and 200 <= status < 300)
    if paired and ok2xx:
        ts = epoch(r["ts"])
        win = _PAIR_WINDOW.get(key, 15.0)
        eid0 = r["thread_id"]
        for name in paired:
            for (t, ev_eid) in event_times.get(name, []):
                if abs(ts - t) <= win and (eid0 is None or ev_eid is None or ev_eid == eid0):
                    return None
    if key in _PRODUCT_LABELS:
        return {"scope": "product", "eid": None, "label": _PRODUCT_LABELS[key],
                "parts": [], "href": product_href(prod_code)}
    scope = r["scope"]
    body = _body(r["payload_json"])
    # khách firebase_key KHÔNG phải số → middleware không gắn scope; vá tại đây
    segs = raw_path.strip("/").split("/")
    if scope is None and len(segs) == 3 and segs[1] == "customers" and segs[2] != "new":
        kh_key = segs[2]
        la = _customer_update_action(body) or ("Sửa khách", "")
        return {"scope": "customer", "eid": kh_key, "label": la[0],
                "parts": [part(la[1])] if la[1] else [], "href": f"#/khach/{kh_key}"}

    # ĐƠN — nhãn/chi tiết như lịch sử đơn
    if scope == "order" or (scope is None and "/api/order/" in raw_path):
        norm = _order_norm(raw_path)
        eid = r["thread_id"]
        if eid is None:
            m = _ORDER_ID.search(raw_path)
            eid = int(m.group(1)) if m else None
        label = _ORDER_LABELS.get(norm)
        if not label:
            label = _EXTRA_LABELS.get(key, "Cập nhật đơn")
            if label is None:
                return None
        detail, parts = _order_detail(norm, body, resolver)
        if not parts and detail:
            parts = [part(detail)]
        return {"scope": "order", "eid": eid, "label": label, "parts": parts,
                "href": href_for("order", eid)}

    # Endpoint có nhãn riêng (kể cả scope=None: bảng giá/thợ/lương/user/kiểm kho…)
    if key in _EXTRA_LABELS:
        label = _EXTRA_LABELS[key]
        if label is None:
            return None
        meta = _generic(r, key, label, body, resolver)
        if key == "POST /api/stocktakes/{id}":   # autosave đếm kiểm kho — gộp liên tiếp
            meta["_rk"] = (key, r["actor_id"], meta.get("eid"))
        return meta

    if scope is None:
        return None   # request lạ không scope → không đoán bừa

    # Scope thực thể — tái dùng phân loại body của lịch sử thực thể
    label, detail = _ent_label(key, method, path), ""
    if key == "POST /api/inventory/box/{id}":
        if "place_id" in body or body.get("clear_place"):
            return None   # box.moved event chi tiết hơn
        la = _box_update_action(body, {})
        if la:
            label, detail = la
    elif key == "POST /api/customers/{id}":
        la = _customer_update_action(body)
        if la:
            label, detail = la
    elif key == "POST /api/tasks/{id}":
        la = _task_update_action(body)
        if la:
            label, detail = la
    elif key == "POST /api/places/{id}":
        la = _place_update_action(body)
        if la:
            label, detail = la
    elif path.endswith("/report"):
        detail = _report_detail(str(body.get("text") or ""))
    elif key == "POST /api/price-lists/{id}/price":
        sp, gia = body.get("sp") or body.get("code"), body.get("price") or body.get("gia")
        detail = f"{sp}: {money(gia)}" if sp else ""
    else:
        detail = str(body.get("text") or body.get("note") or body.get("name") or "")[:50]
    eid = r["thread_id"]
    autosave = path.endswith("/report")   # autosave dồn dập → feed gộp dòng liên tiếp
    return {"scope": scope, "eid": eid, "label": label,
            "parts": [part(detail)] if detail else [], "href": href_for(scope, eid),
            "_rk": (key, r["actor_id"], eid) if autosave else None}


def _generic(r, key: str, label: str, body: dict, resolver) -> dict:
    """Dòng cho endpoint scope=None có nhãn riêng — detail từ body + href suy từ path."""
    raw_path = (r["source"] or "").split(" ", 1)[1].split("?")[0]
    scope = r["scope"] or _scope_of_path(raw_path) or "app"
    eid = r["thread_id"]
    if eid is None:
        m = re.search(r"/(\d+)(?:/|$)", raw_path)
        eid = int(m.group(1)) if m else None
    parts = []
    if key == "POST /api/wages":
        code, luong = body.get("code") or body.get("ma"), body.get("luong") or body.get("wage")
        if code:
            parts = [part(str(code), product_href(code)), part(f": {money(luong)}/1SP" if luong else "")]
    elif key == "POST /api/inventory/bulk-move":
        ids = body.get("box_ids") or []
        pname = resolver.place_name(body.get("place_id")) if resolver else None
        parts = [part(f"{len(ids)} thùng → "), part(pname or "?", href_for("place", body.get("place_id")))]
    elif key == "POST /api/customers/new":
        name = str(body.get("name") or "")[:40]
        if name:
            parts = [part(f"“{name}”")]
    elif key == "POST /api/cashbox/transfer":
        try:
            from cashbox_store.identity import box_display
            parts = [part(f"{box_display(str(body.get('from_box') or ''))} → "
                          f"{box_display(str(body.get('to_box') or ''))}: "),
                     part(money(body.get("amount")))]
            if body.get("note"):
                parts.append(part(f" “{str(body.get('note'))[:40]}”"))
        except Exception:  # noqa: BLE001
            parts = []
    elif key == "POST /api/cashbox/withdraw":
        try:
            from cashbox_store.identity import box_display
            parts = [part(f"{box_display(str(body.get('box') or ''))}: "),
                     part(money(body.get("amount")))]
            if body.get("note"):
                parts.append(part(f" “{str(body.get('note'))[:40]}”"))
        except Exception:  # noqa: BLE001
            parts = []
    elif key.startswith("POST /api/users/"):
        m = re.search(r"/api/users/([^/]+)/", raw_path)
        who = m.group(1) if m else ""
        val = body.get("role") or body.get("disabled")
        parts = [part(f"{who}" + (f" → {val}" if val is not None else ""))]
    else:
        txt = str(body.get("name") or body.get("title") or body.get("label")
                  or body.get("note") or body.get("reason") or "")[:50]
        if txt:
            parts = [part(f"“{txt}”")]
    href = href_for(scope, eid) if scope not in ("app", "user") else ""
    if key == "POST /api/settings":
        href = "#/login"
    if key == "POST /api/quy-cach":
        href = "#/quy-cach"
    if key.startswith("POST /api/cashbox/"):
        href = "#/ket"
    return {"scope": scope, "eid": eid, "label": label, "parts": parts, "href": href}


def row_meta(r, resolver, event_times) -> dict | None:
    """1 audit row → meta feed hiển thị được, kèm nhãn nhóm + detail text."""
    meta = event_row(r, resolver) if r["action"] != "http.request" else http_row(r, resolver, event_times)
    if not meta:
        return None
    meta["scope_label"] = _SCOPE_LABEL.get(meta["scope"], meta["scope"])
    meta["detail"] = parts_text(meta.get("parts") or [])
    return meta
