"""Gửi push FCM (Firebase Cloud Messaging) tới app Android — topic "orders".

Tái dùng app firebase-admin đã init ở integrations/firebase_sync.core (không init
trùng). Best-effort, chạy nền (messaging.send là HTTP blocking → to_thread), không
bao giờ làm hỏng luồng gọi.

MẶC ĐỊNH TẮT — bật bằng env FCM_ENABLED=true SAU KHI APK đã tích hợp FCM SDK +
subscribeToTopic("orders"). Trước đó gửi sẽ vô ích (không ai nhận) nên để tắt cho
đỡ rác log. APK: thêm FirebaseMessagingService, subscribe topic FCM_TOPIC.
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("server")

FCM_TOPIC = os.getenv("FCM_TOPIC", "orders")
FCM_ENABLED = os.getenv("FCM_ENABLED", "false").strip().lower() in ("1", "true", "yes")


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
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body, image=image_url or None),
            data={k: str(v) for k, v in (data or {}).items()},
            topic=FCM_TOPIC,
            android=android,
        )
        messaging.send(msg, app=app)
        log.info("FCM sent: %s%s", title, " (+img)" if image_url else "")
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
