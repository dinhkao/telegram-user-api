"""Best-effort Google Sheet sync khi webapp thêm số lượng nhận vào phiếu SX.

Nhân bản luồng sheets_bot.handle_amount (gõ số trong topic → ghi 1 import row
vào Google Sheet), nhưng kích hoạt từ POST /api/production/{id}/number. Chạy nền,
KHÔNG chặn phản hồi. No-op êm nếu thiếu Google creds (SheetsManager dựng được
nhưng API call sẽ hỏng → nuốt lỗi). Kết nối: sheets_bot.sheets.SheetsManager,
server_app.tasks.spawn_tracked.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("production")
_VN_TZ = timezone(timedelta(hours=7))

_manager = None
_unavailable = False


def _get_manager():
    global _manager, _unavailable
    if _unavailable:
        return None
    if _manager is not None:
        return _manager
    try:
        from sheets_bot.sheets.manager import SheetsManager
        _manager = SheetsManager()
        return _manager
    except Exception as e:  # noqa: BLE001 — sync là best-effort
        log.info("production sheet sync tắt (không dựng được SheetsManager): %s", e)
        _unavailable = True
        return None


async def _sync(thread_id, amount: float, note: str, actor: str) -> None:
    mgr = _get_manager()
    if mgr is None:
        return
    try:
        info = await mgr.lookup_production_by_thread_id(str(thread_id))
        if not info or not info.get("productCode"):
            log.info("sheet sync: không thấy productCode cho thread %s", thread_id)
            return
        msg = {
            "date": datetime.now(_VN_TZ),
            "sender_name": actor,
            "message_id": 0,          # nguồn webapp — không có message id Telegram
            "message_thread_id": thread_id,
            "message_deep_link": "",
        }
        await mgr.append_import_row(msg, {"amount": amount, "note": note}, info)
        log.info("sheet sync ok thread=%s amount=%s", thread_id, amount)
    except Exception as e:  # noqa: BLE001
        log.warning("sheet sync hỏng thread=%s: %s", thread_id, e)


def sync_number_bg(thread_id, amount: float, note: str, request) -> None:
    """Lên lịch ghi Google Sheet chạy nền (không await trong đường HTTP)."""
    actor = "web"
    user = request.get("web_user") if request is not None else None
    if isinstance(user, dict):
        actor = str(user.get("name") or user.get("username") or "web")
    elif user:
        actor = str(user)
    from server_app.tasks import spawn_tracked
    spawn_tracked("production.sheet_sync", _sync(thread_id, amount, note, actor))


async def push_report(thread_id, text: str) -> dict:
    """Đẩy báo cáo theo thợ vào Google Sheet (tab theo ngày) qua append_rows —
    tái dùng pipeline sheets_bot: tạo tab ngày, header, công thức lương, sắp theo
    STT, GHI ĐÈ dòng cũ cùng topic (idempotent theo thread_url). Ô ; ánh xạ thẳng
    HEADERS. Trả trạng thái rõ ràng để webapp báo thành công/thất bại:
      {ok, disabled?, error?, tab?, rows?, replaced?}
    """
    mgr = _get_manager()
    if mgr is None:
        return {"ok": False, "disabled": True, "error": "Google Sheet chưa cấu hình (thiếu credentials)"}
    try:
        rows = [[c.strip() for c in line.split(";")] for line in text.splitlines() if line.strip()]
        if not rows:
            return {"ok": False, "error": "Không có dòng dữ liệu để đẩy"}
        from command_handlers.production_commands import _topic_link
        thread_url = _topic_link(thread_id)
        result = await mgr.append_rows(rows, thread_url)
        from sheets_bot.parse import get_sheet_name_from_rows
        tab = get_sheet_name_from_rows(rows)
        replaced = bool(result and result.get("replaced"))
        log.info("sheet report push ok thread=%s tab=%s rows=%s replaced=%s",
                 thread_id, tab, len(rows), replaced)
        return {"ok": True, "tab": tab, "rows": len(rows), "replaced": replaced}
    except Exception as e:  # noqa: BLE001
        log.warning("sheet report push hỏng thread=%s: %s", thread_id, e)
        return {"ok": False, "error": str(e)}
