"""Nhắc CÔNG NỢ QUÁ HẠN mỗi ngày — vòng lặp nền, chạy từ bootstrap.

Mỗi ngày (từ `DEBT_ALERT_HOUR`, mặc định 8h sáng VN) quét 1 lượt
`debt_alert.compute_debt_alerts` rồi ghi **1 thông báo / 1 khách** qua
`server_app.notify.push_bg` → vào trung tâm thông báo trong app + push FCM.
Khách còn nợ thì NGÀY NÀO CŨNG được nhắc lại cho tới khi hết nợ.

Chống spam / chống nhắc lại khi restart: ngày đã gửi ghi vào `kv_store` (app.db,
path `debt_alert_state`), 1 lượt/ngày kể cả process khởi động lại nhiều lần.
Quá `DEBT_ALERT_MAX_PUSH` khách thì gộp phần dư vào 1 thông báo tổng.

Nối: server_app.debt_alert (luật), server_app.notify (ghi + FCM), utils.db.
Đăng ký: server_app/bootstrap.py (spawn_tracked "debt_alert.daily").
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime

from utils.db import get_connection
from server_app.debt_alert import _VN_TZ, alert_line, compute_debt_alerts, money_vn, today_vn

log = logging.getLogger("server")

_KV_PATH = "debt_alert_state"
_CHECK_EVERY = 10 * 60           # nhịp kiểm tra (giây)
ALERT_HOUR = int(os.getenv("DEBT_ALERT_HOUR", "8") or 8)          # giờ VN bắt đầu nhắc
MAX_PUSH = int(os.getenv("DEBT_ALERT_MAX_PUSH", "8") or 8)        # số thông báo lẻ tối đa/ngày
MIN_DAYS = int(os.getenv("DEBT_ALERT_MIN_DAYS", "1") or 1)        # nợ từ mấy ngày thì nhắc


def _read_state() -> dict:
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS kv_store (path TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
        row = conn.execute("SELECT value FROM kv_store WHERE path = ?", (_KV_PATH,)).fetchone()
        if not row or not row[0]:
            return {}
        data = json.loads(row[0])
        return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001 — trạng thái nhắc hỏng không được làm chết loop
        log.warning("debt_alert: đọc trạng thái lỗi: %s", e)
        return {}
    finally:
        conn.close()


def _write_state(state: dict) -> None:
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS kv_store (path TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
        conn.execute(
            "INSERT INTO kv_store(path, value, updated_at) VALUES (?, ?, strftime('%s','now')) "
            "ON CONFLICT(path) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (_KV_PATH, json.dumps(state, ensure_ascii=False)),
        )
        conn.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("debt_alert: ghi trạng thái lỗi: %s", e)
    finally:
        conn.close()


def _scan(min_days: int) -> dict:
    from order_db import _get_connection
    conn = _get_connection()
    try:
        return compute_debt_alerts(conn, min_days)
    finally:
        conn.close()


def _push_alerts(alerts: list[dict], total: int) -> int:
    """Ghi thông báo (app + FCM) cho từng khách; phần dư gộp 1 dòng. Trả số đã gửi.

    PHẢI gọi trên event loop (push_bg = asyncio.create_task) — không bọc to_thread."""
    from server_app.notify import push_bg
    shown = alerts[:MAX_PUSH]
    for a in shown:
        push_bg(
            f"Công nợ quá hạn · {a['name']}",
            alert_line(a),
            {"type": "debt", "thread_id": a["source_thread_id"], "customer_key": a["key"]},
        )
    rest = alerts[MAX_PUSH:]
    if rest:
        push_bg(
            f"Và {len(rest)} khách nợ quá hạn nữa",
            f"Tổng {len(alerts)} khách đang nợ quá hạn · {money_vn(total)}. Mở trang Nợ quá hạn để xem hết.",
            {"type": "debt"},
        )
    return len(shown) + (1 if rest else 0)


async def _tick() -> None:
    now = datetime.now(_VN_TZ)
    if now.hour < ALERT_HOUR:
        return
    day = now.date().isoformat()
    state = await asyncio.to_thread(_read_state)
    if state.get("last_sent") == day:
        return
    res = await asyncio.to_thread(_scan, MIN_DAYS)
    alerts = res.get("alerts") or []
    # Đánh dấu ĐÃ CHẠY hôm nay kể cả khi không có ai nợ → đúng 1 lượt/ngày.
    await asyncio.to_thread(_write_state, {"last_sent": day, "count": len(alerts)})
    if not alerts:
        log.info("debt_alert: %s — không có khách nợ quá hạn", day)
        return
    sent = _push_alerts(alerts, res.get("total") or 0)   # trên loop: push_bg tự chạy nền
    log.info("debt_alert: %s — %d khách nợ quá hạn, đã đẩy %d thông báo", day, len(alerts), sent)


async def debt_alert_loop() -> None:
    """Vòng lặp nền: cứ 10 phút kiểm tra, mỗi ngày nhắc đúng 1 lượt."""
    log.info("debt_alert: bật nhắc nợ quá hạn (từ %dh, nợ ≥ %d ngày)", ALERT_HOUR, MIN_DAYS)
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — không bao giờ để loop chết
            log.error("debt_alert tick lỗi: %s", e, exc_info=True)
        await asyncio.sleep(_CHECK_EVERY)


__all__ = ["debt_alert_loop", "today_vn"]
