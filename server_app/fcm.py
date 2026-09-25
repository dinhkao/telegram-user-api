"""Gửi push FCM (Firebase Cloud Messaging) tới app Android.

Hai đường gửi, chạy nối tiếp trong cùng một lần push:
1. **THEO TOKEN từng máy** (chính) — token do APK đăng ký qua POST /api/fcm/register,
   lưu ở bảng `fcm_tokens` (notif_store.fcm_tokens). Nhờ vậy LỌC ĐƯỢC người nhận:
   user vai trò bó hẹp `chat_luong` và user bị khoá KHÔNG nhận push nào.
2. **TOPIC chung** ("orders") — giữ làm FALLBACK cho máy chưa cập nhật APK (chưa biết
   gửi token). Tắt bằng env FCM_TOPIC_FALLBACK=false khi mọi máy đã lên bản mới. APK
   mới đã unsubscribe topic nên không bị push đúp.

Tái dùng app firebase-admin đã init ở integrations/firebase_sync.core (không init
trùng). `send_once` blocking (gọi qua to_thread), không bao giờ raise: thử lại tức thì
khi lỗi tạm rồi trả phần CÒN THIẾU (token/topic) cho server_app.push_outbox gửi bù.

MẶC ĐỊNH TẮT — bật bằng env FCM_ENABLED=true SAU KHI APK đã tích hợp FCM SDK.
Kết nối: notif_store.fcm_tokens, server_app.web_auth.role_scope (tên vai trò bị loại).
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("server")

FCM_TOPIC = os.getenv("FCM_TOPIC", "orders")
FCM_ENABLED = os.getenv("FCM_ENABLED", "false").strip().lower() in ("1", "true", "yes")
# Gửi kèm topic cũ cho máy chưa cập nhật APK. Tắt khi mọi máy đã đăng ký token.
FCM_TOPIC_FALLBACK = os.getenv("FCM_TOPIC_FALLBACK", "true").strip().lower() in ("1", "true", "yes")

_BATCH = 500   # trần của send_each_for_multicast
# Lỗi = token CHẾT (máy gỡ app / token đổi / sai project) → xoá khỏi bảng. Nhận diện
# theo TÊN LỚP ngoại lệ vì .code của firebase-admin là mã chung (UnregisteredError →
# 'NOT_FOUND', SenderIdMismatchError → 'PERMISSION_DENIED'), không phải tên lỗi FCM.
_DEAD_EXC_NAMES = ("UNREGISTEREDERROR", "SENDERIDMISMATCHERROR")
_DEAD_CODES = ("UNREGISTERED", "SENDER_ID_MISMATCH", "INVALID_ARGUMENT")


def _eligible_rows(audience: str | None = None) -> list[tuple[str, str]]:
    """(token, username) của user ĐƯỢC nhận push (bỏ vai trò bó hẹp + user bị khoá).
    audience='office' → CHỈ văn phòng (admin/van_phong)."""
    try:
        from notif_store.fcm_tokens import eligible_rows
        from server_app.web_auth.role_scope import QUALITY_ONLY_ROLE
        from utils.db import get_connection
        conn = get_connection()
        try:
            rows = eligible_rows(conn, exclude_roles=(QUALITY_ONLY_ROLE,))
            if audience == "office":
                from user_store import OFFICE_ROLES
                ph = ",".join("?" * len(OFFICE_ROLES))
                office = {r[0] for r in conn.execute(
                    f"SELECT username FROM web_users WHERE role IN ({ph})", tuple(OFFICE_ROLES)).fetchall()}
                rows = [r for r in rows if r[1] in office]
            return rows
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("FCM tokens read failed: %s", e)
        return []


def _drop_dead(tokens: list[str]) -> None:
    if not tokens:
        return
    try:
        from notif_store.fcm_tokens import delete_tokens
        from utils.db import get_connection
        conn = get_connection()
        try:
            delete_tokens(conn, tokens)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("FCM dead-token cleanup failed: %s", e)


def _is_dead_token(resp) -> bool:
    exc = getattr(resp, "exception", None)
    if exc is None:
        return False
    if type(exc).__name__.upper() in _DEAD_EXC_NAMES:
        return True
    code = str(getattr(exc, "code", "") or "").upper().replace("-", "_")
    return code in _DEAD_CODES


def _multicast(messaging, app, notification, payload, android, tokens: list[str]):
    """1 lượt gửi cho `tokens` (chia lô ≤500). Trả (ok, fail, dead) = danh sách TOKEN.
    Lỗi mạng cả lượt → raise (người gọi thử lại)."""
    ok: list[str] = []
    fail: list[str] = []
    dead: list[str] = []
    for i in range(0, len(tokens), _BATCH):
        batch = tokens[i:i + _BATCH]
        msg = messaging.MulticastMessage(
            notification=notification, data=payload, android=android, tokens=batch
        )
        resp = messaging.send_each_for_multicast(msg, app=app)
        for tok, r in zip(batch, resp.responses, strict=False):
            if getattr(r, "success", False):
                ok.append(tok)
            elif _is_dead_token(r):
                dead.append(tok)
            else:
                fail.append(tok)
    return ok, fail, dead


# Thử lại NGAY trong 1 lần gửi khi lỗi tạm (mạng chập, FCM 5xx/quota, 1 máy lỗi tạm):
# chờ lần lượt các mốc này rồi thử lại phần CÒN THIẾU. Hết lượt thì trả về phần còn thiếu
# để server_app.push_outbox gửi bù về sau (hàng đợi bền, qua cả restart).
_INNER_WAITS = (2, 5)


def send_once(title: str, body: str, data: dict | None = None, image_url: str | None = None,
              tokens: list[str] | None = None, topic: bool = True, audience: str | None = None) -> dict:
    """Gửi 1 push (blocking — gọi qua to_thread). tokens=None → MỌI máy đủ điều kiện;
    list → chỉ các token đó (còn đủ điều kiện). Trả {ok_users, fail_users, pending_tokens
    (None = chưa tới được máy nào, gửi lại cho MỌI máy), topic_pending, error, disabled,
    no_app}. Không bao giờ raise."""
    import time as _t
    res = {"ok_users": [], "fail_users": [], "pending_tokens": [], "topic_pending": False,
           "error": None, "disabled": False, "no_app": False}
    if not FCM_ENABLED:
        res["disabled"] = True
        return res
    try:
        from integrations.firebase_sync.core import _get_app
        from firebase_admin import messaging
        app = _get_app()
    except Exception as e:  # noqa: BLE001
        # pending_tokens=None = CHƯA gửi được máy nào → lần sau gửi lại cho MỌI máy
        res.update(error=f"init: {e}", pending_tokens=None if tokens is None else list(tokens),
                   topic_pending=topic and FCM_TOPIC_FALLBACK)
        return res
    if app is None:
        res.update(no_app=True, error="firebase app chưa sẵn sàng",
                   pending_tokens=None if tokens is None else list(tokens),
                   topic_pending=topic and FCM_TOPIC_FALLBACK)
        return res
    android = messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(image=image_url) if image_url else None,
    )
    payload = {k: str(v) for k, v in (data or {}).items()}
    if image_url:
        payload.setdefault("image_url", image_url)
    notification = messaging.Notification(title=title, body=body, image=image_url or None)

    rows = _eligible_rows(audience)
    users = dict(rows)
    todo = [t for t, _ in rows] if tokens is None else [t for t in tokens if t in users]
    ok_tok: list[str] = []
    dead_all: list[str] = []
    for n in range(len(_INNER_WAITS) + 1):
        if not todo:
            break
        try:
            ok, fail, dead = _multicast(messaging, app, notification, payload, android, todo)
            ok_tok += ok
            dead_all += dead
            todo = fail
            res["error"] = None
        except Exception as e:  # noqa: BLE001 — lỗi mạng cả lượt → thử lại cả phần còn thiếu
            res["error"] = f"multicast: {e}"
        if todo and n < len(_INNER_WAITS):
            _t.sleep(_INNER_WAITS[n])
    _drop_dead(dead_all)
    res["ok_users"] = sorted(users.get(t, "?") for t in ok_tok)
    res["fail_users"] = sorted(users.get(t, "?") for t in todo)
    res["pending_tokens"] = todo

    if topic and FCM_TOPIC_FALLBACK:
        res["topic_pending"] = True
        for n in range(len(_INNER_WAITS) + 1):
            try:
                messaging.send(messaging.Message(notification=notification, data=payload,
                                                 topic=FCM_TOPIC, android=android), app=app)
                res["topic_pending"] = False
                break
            except Exception as e:  # noqa: BLE001
                res["error"] = (res["error"] + " | " if res["error"] else "") + f"topic: {e}"
                if n < len(_INNER_WAITS):
                    _t.sleep(_INNER_WAITS[n])
    log.info("FCM sent: %s%s — máy nhận: %s%s%s", title, " (+img)" if image_url else "",
             ", ".join(res["ok_users"]) or "(không máy nào)",
             f" | CHƯA NHẬN: {', '.join(res['fail_users'])}" if res["fail_users"] else "",
             " | topic LỖI" if res["topic_pending"] else "")
    if res["error"]:
        log.warning("FCM lỗi (sẽ gửi bù nếu còn thiếu): %s", res["error"])
    return res


async def notify(title: str, body: str, data: dict | None = None, image_url: str | None = None) -> dict:
    """Gửi 1 lần (kèm thử lại tức thì), KHÔNG qua hàng đợi bền. Đường chính dùng
    server_app.notify.push_bg (có gửi bù); hàm này chỉ là dự phòng khi ghi DB lỗi."""
    return await asyncio.to_thread(send_once, title, body, data, image_url)


def notify_bg(title: str, body: str, data: dict | None = None, image_url: str | None = None) -> None:
    """Lên lịch gửi FCM chạy nền (không chặn). Dự phòng — xem notify()."""
    if not FCM_ENABLED:
        return
    from server_app.tasks import spawn_tracked
    spawn_tracked("fcm.notify", notify(title, body, data, image_url))
