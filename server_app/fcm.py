"""Gửi push FCM (Firebase Cloud Messaging) tới app Android.

Hai đường gửi, chạy nối tiếp trong cùng một lần push:
1. **THEO TOKEN từng máy** (chính) — token do APK đăng ký qua POST /api/fcm/register,
   lưu ở bảng `fcm_tokens` (notif_store.fcm_tokens). Nhờ vậy LỌC ĐƯỢC người nhận:
   user vai trò bó hẹp `chat_luong` và user bị khoá KHÔNG nhận push nào.
2. **TOPIC chung** ("orders") — giữ làm FALLBACK cho máy chưa cập nhật APK (chưa biết
   gửi token). Tắt bằng env FCM_TOPIC_FALLBACK=false khi mọi máy đã lên bản mới. APK
   mới đã unsubscribe topic nên không bị push đúp.

Tái dùng app firebase-admin đã init ở integrations/firebase_sync.core (không init
trùng). Best-effort, chạy nền (messaging.send là HTTP blocking → to_thread), không
bao giờ làm hỏng luồng gọi.

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


def _eligible_rows() -> list[tuple[str, str]]:
    """(token, username) của user ĐƯỢC nhận push (bỏ vai trò bó hẹp + user bị khoá)."""
    try:
        from notif_store.fcm_tokens import eligible_rows
        from server_app.web_auth.role_scope import QUALITY_ONLY_ROLE
        from utils.db import get_connection
        conn = get_connection()
        try:
            return eligible_rows(conn, exclude_roles=(QUALITY_ONLY_ROLE,))
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


def _send_tokens(messaging, app, notification, payload, android,
                 rows: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """Gửi theo từng token (chia lô ≤500). Trả (tên người NHẬN, tên người LỖI) + dọn
    token chết. Trả TÊN chứ không phải số: "token 4 ok" không cho biết máy của ai
    vắng mặt — mà đó chính là câu hỏi khi có người kêu không nhận được push."""
    ok: list[str] = []
    fail: list[str] = []
    dead: list[str] = []
    tokens = [t for t, _ in rows]
    users = dict(rows)
    for i in range(0, len(tokens), _BATCH):
        batch = tokens[i:i + _BATCH]
        msg = messaging.MulticastMessage(
            notification=notification, data=payload, android=android, tokens=batch
        )
        resp = messaging.send_each_for_multicast(msg, app=app)
        for tok, r in zip(batch, resp.responses, strict=False):
            who = users.get(tok, "?")
            if getattr(r, "success", False):
                ok.append(who)
                continue
            fail.append(who)
            if _is_dead_token(r):
                dead.append(tok)
    _drop_dead(dead)
    return ok, fail


def _send(title: str, body: str, data: dict | None = None, image_url: str | None = None) -> None:
    try:
        from integrations.firebase_sync.core import _get_app
        from firebase_admin import messaging
        app = _get_app()
        if app is None:
            return
        # image_url → big-picture trên Android (kèm large-icon cho gọn). Cross-platform
        # Notification.image cũng map sang bigPicture nhưng đặt rõ trong AndroidConfig.
        android = messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(image=image_url) if image_url else None,
        )
        # data['image_url'] cũng gửi kèm để foreground handler (FcmMessagingService) đọc
        # được chắc chắn — không phụ thuộc riêng notification.imageUrl (SDK foreground
        # đôi khi không map). Noti nền vẫn dùng Notification.image như cũ.
        payload = {k: str(v) for k, v in (data or {}).items()}
        if image_url:
            payload.setdefault("image_url", image_url)
        notification = messaging.Notification(title=title, body=body, image=image_url or None)

        rows = _eligible_rows()
        if rows:
            try:
                ok, fail = _send_tokens(messaging, app, notification, payload, android, rows)
                log.info("FCM sent: %s%s — máy nhận: %s%s", title,
                         " (+img)" if image_url else "",
                         ", ".join(sorted(ok)) or "(không máy nào)",
                         f" | LỖI: {', '.join(sorted(fail))}" if fail else "")
            except Exception as e:  # noqa: BLE001
                log.warning("FCM multicast failed: %s", e)

        if FCM_TOPIC_FALLBACK:
            msg = messaging.Message(
                notification=notification, data=payload, topic=FCM_TOPIC, android=android,
            )
            messaging.send(msg, app=app)
            log.info("FCM sent (topic %s): %s%s", FCM_TOPIC, title, " (+img)" if image_url else "")
    except Exception as e:
        log.warning("FCM send failed: %s", e)


async def notify(title: str, body: str, data: dict | None = None, image_url: str | None = None) -> None:
    if not FCM_ENABLED:
        return
    await asyncio.to_thread(_send, title, body, data, image_url)


def notify_bg(title: str, body: str, data: dict | None = None, image_url: str | None = None) -> None:
    """Lên lịch gửi FCM chạy nền (không chặn). Gọi từ handler async. image_url =
    ảnh big-picture (Android) — None thì push thường."""
    if not FCM_ENABLED:
        return
    from server_app.tasks import spawn_tracked
    spawn_tracked("fcm.notify", notify(title, body, data, image_url))
