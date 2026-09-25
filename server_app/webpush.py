"""Gửi WEB PUSH (chuẩn VAPID) — cho iPhone (PWA "Thêm vào màn hình chính", iOS ≥ 16.4) và
trình duyệt không có APK. Chạy SONG SONG với FCM trong cùng hàng đợi push bền
(server_app.push_outbox): `send_once` blocking (gọi qua to_thread), không bao giờ raise —
thử lại tức thì khi lỗi tạm (mạng / 429 / 5xx), xoá đăng ký CHẾT (404/410), trả phần còn
thiếu để outbox gửi bù. Người nhận lọc y như FCM (notif_store.webpush_subs).

Khoá VAPID: file PEM ở utils.paths.VAPID_PRIVATE_KEY_FILE (tạo bằng tools/gen_vapid_key.py);
thiếu file = web push tắt. Tắt hẳn: env WEBPUSH_ENABLED=false.
Payload gửi tới service worker (webapp/public/sw.js): {title, body, url, tag}.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from functools import lru_cache
from urllib.parse import urlparse

from utils.paths import VAPID_PRIVATE_KEY_FILE

log = logging.getLogger("server")

WEBPUSH_ENABLED = os.getenv("WEBPUSH_ENABLED", "true").strip().lower() in ("1", "true", "yes")
# Dịch vụ push hợp lệ — server CHỈ POST tới các host này (chặn SSRF: endpoint do client gửi lên)
ALLOWED_PUSH_HOSTS = ("web.push.apple.com", "fcm.googleapis.com", "updates.push.services.mozilla.com",
                      "push.services.mozilla.com")
_INNER_WAITS = (2, 5)
_TTL = 12 * 3600


def endpoint_allowed(endpoint: str) -> bool:
    try:
        u = urlparse(endpoint)
    except Exception:  # noqa: BLE001
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and (host in ALLOWED_PUSH_HOSTS or host.endswith(".notify.windows.com"))


def _subject() -> str:
    base = os.getenv("WEBAPP_URL", "").strip()
    u = urlparse(base) if base else None
    return f"{u.scheme}://{u.netloc}" if u and u.scheme == "https" and u.netloc else "mailto:admin@localhost"


@lru_cache(maxsize=1)
def _vapid():
    from py_vapid import Vapid
    return Vapid.from_file(VAPID_PRIVATE_KEY_FILE)


def enabled() -> bool:
    return WEBPUSH_ENABLED and os.path.isfile(VAPID_PRIVATE_KEY_FILE)


def public_key() -> str:
    """Khoá công khai (base64url, điểm EC không nén) cho pushManager.subscribe phía client."""
    from cryptography.hazmat.primitives import serialization
    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def target_url(data: dict | None) -> str:
    """Đường dẫn mở khi bấm thông báo: route (thông báo ngoài đơn) > đơn (+focus)."""
    d = data or {}
    route = str(d.get("route") or "")
    if route.startswith("#/"):
        return "/app/" + route
    tid = str(d.get("thread_id") or "")
    if tid:
        t, cid = d.get("type"), d.get("comment_id") or d.get("image_id")
        return f"/app/#/order/{tid}" + (f"?focus={t}:{cid}" if t and cid else "")
    return "/app/"


def _eligible(audience: str | None) -> list[dict]:
    try:
        from notif_store.webpush_subs import eligible_subs
        from server_app.web_auth.role_scope import QUALITY_ONLY_ROLE
        from utils.db import get_connection
        conn = get_connection()
        try:
            if audience == "office":
                from user_store import OFFICE_ROLES
                return eligible_subs(conn, exclude_roles=(QUALITY_ONLY_ROLE,), only_roles=tuple(OFFICE_ROLES))
            return eligible_subs(conn, exclude_roles=(QUALITY_ONLY_ROLE,))
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("webpush subs read failed: %s", e)
        return []


def _drop(endpoints: list[str]) -> None:
    if not endpoints:
        return
    try:
        from notif_store.webpush_subs import delete_subs
        from utils.db import get_connection
        conn = get_connection()
        try:
            delete_subs(conn, endpoints)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("webpush dead-sub cleanup failed: %s", e)


def _push_one(sub: dict, payload: str) -> str:
    """'ok' | 'dead' (xoá đăng ký) | 'fail' (lỗi tạm — thử lại)."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload, vapid_private_key=_vapid(), vapid_claims={"sub": _subject()},
                ttl=_TTL, headers={"Urgency": "high"}, timeout=10)
        return "ok"
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (404, 410):          # máy gỡ app / huỷ quyền → xoá đăng ký
            return "dead"
        if code == 413:                 # payload quá lớn — gửi lại cũng vậy, bỏ
            log.warning("webpush 413 bỏ qua: %s", e)
            return "ok"
        # 400/403 thường do CẤU HÌNH phía mình (khoá VAPID/JWT) — KHÔNG xoá đăng ký
        # (sai cấu hình mà xoá thì mất sạch máy của mọi người), để gửi bù + log lỗi.
        log.warning("webpush lỗi %s: %s", code, e)
        return "fail"
    except Exception:  # noqa: BLE001 — mạng
        return "fail"


def send_once(title: str, body: str, data: dict | None = None, endpoints: list[str] | None = None,
              audience: str | None = None) -> dict:
    """Gửi web push. endpoints=None → MỌI đăng ký đủ điều kiện; list → chỉ các endpoint đó.
    Trả {ok_users, fail_users, pending (list endpoint còn thiếu), disabled}. Không raise."""
    res = {"ok_users": [], "fail_users": [], "pending": [], "disabled": False, "error": None}
    if not enabled():
        res["disabled"] = True
        return res
    subs = _eligible(audience)
    if endpoints is not None:
        want = set(endpoints)
        subs = [s for s in subs if s["endpoint"] in want]
    if not subs:
        return res
    payload = json.dumps({"title": title, "body": body, "url": target_url(data),
                          "tag": f"n{int(time.time() * 1000)}"}, ensure_ascii=False)
    todo, ok, dead = subs, [], []
    for n in range(len(_INNER_WAITS) + 1):
        nxt = []
        for s in todo:
            r = _push_one(s, payload)
            (ok if r == "ok" else dead if r == "dead" else nxt).append(s)
        todo = nxt
        if todo and n < len(_INNER_WAITS):
            time.sleep(_INNER_WAITS[n])
    _drop([s["endpoint"] for s in dead])
    res["ok_users"] = sorted(s["username"] for s in ok)
    res["fail_users"] = sorted(s["username"] for s in todo)
    res["pending"] = [s["endpoint"] for s in todo]
    if todo:
        res["error"] = "webpush lỗi tạm"
    log.info("WebPush sent: %s — máy nhận: %s%s", title, ", ".join(res["ok_users"]) or "(không máy nào)",
             f" | CHƯA NHẬN: {', '.join(res['fail_users'])}" if res["fail_users"] else "")
    return res
