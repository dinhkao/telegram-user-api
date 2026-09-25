"""HÀNG ĐỢI PUSH BỀN — mọi thông báo (server_app.notify.push_bg) đi qua đây để push
FCM không rơi mất: lỗi mạng tới Google, FCM lỗi tạm, 1 máy lỗi tạm, hay server khởi
động lại giữa chừng đều được GỬI BÙ, chỉ tới đúng những máy CHƯA nhận.

Luồng: notify ghi row notifications + push_state='pending' → deliver() gửi ngay
(fcm.send_once đã thử lại tức thì 3 lượt) → lưu trạng thái. Còn thiếu → 'retry' với
mốc thử lại lùi dần; `push_retry_loop` (bootstrap) quét mỗi 30s gửi bù, kể cả row
'pending' bị bỏ dở do restart. Quá 6 giờ → 'failed' (tin cũ gửi muộn là vô nghĩa).
Luật trạng thái thuần: `next_state` (tests/test_push_outbox.py).
Nối: notif_store.push_state, server_app.fcm.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from utils.db import get_connection

log = logging.getLogger("server")

_BACKOFF = (30, 60, 120, 300, 600, 1200, 1800)   # giây chờ trước lần gửi bù thứ 1, 2, …
MAX_ATTEMPTS = len(_BACKOFF) + 1
WINDOW_HOURS = 6
_FIRST_GRACE = 90   # row 'pending' mới tạo: vòng quét chỉ đụng tới sau ngần này giây
_TICK = 30
_locks: dict[int, asyncio.Lock] = {}


def next_state(payload: dict, res: dict, attempts: int) -> tuple[str, dict, int | None, str]:
    """THUẦN: (state, payload mới, giây chờ lần sau | None, tóm tắt) sau 1 lần gửi."""
    if res.get("disabled"):
        return "disabled", payload, None, "FCM tắt (FCM_ENABLED=false)"
    new = dict(payload)
    new["tokens"] = res.get("pending_tokens")      # None = chưa tới máy nào → gửi lại tất cả
    new["topic"] = bool(res.get("topic_pending"))
    parts = []
    if res.get("ok_users"):
        parts.append("nhận: " + ", ".join(res["ok_users"]))
    if res.get("fail_users"):
        parts.append("chưa nhận: " + ", ".join(res["fail_users"]))
    if res.get("error"):
        parts.append("lỗi: " + str(res["error"])[:300])
    summary = " | ".join(parts) or "không có máy nào đăng ký"
    done = new["tokens"] == [] and not new["topic"]
    if done:
        return "sent", new, None, summary
    if attempts >= MAX_ATTEMPTS:
        return "failed", new, None, summary
    return "retry", new, _BACKOFF[min(attempts - 1, len(_BACKOFF) - 1)], summary


def _since_iso() -> str:
    return (datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


async def deliver(notif_id: int) -> None:
    """Gửi (hoặc gửi bù) push của 1 thông báo. Không bao giờ raise."""
    lock = _locks.setdefault(notif_id, asyncio.Lock())
    if lock.locked():
        return                     # đang gửi ở chỗ khác (lần đầu ↔ vòng quét)
    async with lock:
        try:
            from notif_store.push_state import load, save_attempt
            from server_app.fcm import send_once

            def _load():
                conn = get_connection()
                try:
                    return load(conn, notif_id)
                finally:
                    conn.close()
            st = await asyncio.to_thread(_load)
            if not st or st["state"] not in ("pending", "retry"):
                return
            p = st["payload"]
            res = await asyncio.to_thread(send_once, p.get("title", ""), p.get("body", ""), p.get("data"),
                                          p.get("image_url"), p.get("tokens"), bool(p.get("topic", True)),
                                          p.get("audience"))
            attempts = st["attempts"] + 1
            state, newp, wait, summary = next_state(p, res, attempts)
            if state == "failed":
                log.error("PUSH HỎNG sau %d lần #%s «%s»: %s", attempts, notif_id, p.get("title"), summary)
            elif state == "retry":
                log.warning("Push #%s «%s» còn thiếu — gửi bù sau %ss (lần %d): %s",
                            notif_id, p.get("title"), wait, attempts, summary)

            def _save():
                conn = get_connection()
                try:
                    save_attempt(conn, notif_id, state=state, attempts=attempts, payload=newp,
                                 next_at=int(time.time()) + wait if wait else None, result=summary)
                finally:
                    conn.close()
            await asyncio.to_thread(_save)
        except Exception as e:  # noqa: BLE001 — row vẫn 'pending/retry' → vòng quét thử lại
            log.warning("push_outbox deliver #%s lỗi: %s", notif_id, e)
        finally:
            _locks.pop(notif_id, None)


def first_next_at() -> int:
    return int(time.time()) + _FIRST_GRACE


async def push_retry_loop() -> None:
    """Vòng nền: gửi bù push còn thiếu / bị bỏ dở (restart). Không bao giờ chết."""
    from notif_store import create_notif_table
    from notif_store.push_state import due_ids, expire_old
    log.info("push_outbox: bật gửi bù push (quét %ss, cửa sổ %sh)", _TICK, WINDOW_HOURS)
    while True:
        try:
            def _due():
                conn = get_connection()
                try:
                    create_notif_table(conn)
                    since = _since_iso()
                    n = expire_old(conn, since)
                    if n:
                        log.error("push_outbox: %d push quá %sh chưa gửi được → failed", n, WINDOW_HOURS)
                    return due_ids(conn, int(time.time()), since)
                finally:
                    conn.close()
            for nid in await asyncio.to_thread(_due):
                await deliver(nid)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("push_retry_loop lỗi: %s", e, exc_info=True)
        await asyncio.sleep(_TICK)
