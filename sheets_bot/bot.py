"""sheets_bot.bot — Telethon bot entrypoint.

`start_sheets_bot(api_id, api_hash)` creates a bot-token Telethon client, wires
the message dispatch (mirroring bot.js `bot.on('message')`), runs the startup
managed-sheet migration, and returns the client. If no bot token OR no Google
credentials are configured, it logs a warning and returns None without starting.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile

from telethon import TelegramClient, events

from . import config
from .parse import (
    build_html,
    filter_export_columns,
    format_import_row_message,
    format_sheet_name_from_compact_date,
    normalize_product_code,
    parse_leading_amount,
    parse_quoted_payload,
    trim_trailing_empty_rows,
)

log = logging.getLogger("sheets_bot.bot")

_client: TelegramClient | None = None
_manager = None  # SheetsManager, created at start time


# ---------------------------------------------------------------------------
# Telethon message -> normalized context (mirrors node `msg`)
# ---------------------------------------------------------------------------
def _thread_id(message):
    r = getattr(message, "reply_to", None)
    if r is not None and getattr(r, "forum_topic", False):
        return getattr(r, "reply_to_top_id", None) or getattr(r, "reply_to_msg_id", None)
    return None


def _format_sender_name(sender) -> str:
    if not sender:
        return ""
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    full = " ".join(
        p for p in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if p
    )
    return full or str(getattr(sender, "id", "") or "")


def _internal_id(chat_id) -> str:
    internal = str(abs(int(chat_id)))
    if internal.startswith("100"):
        internal = internal[3:]
    return internal


def _build_thread_url(chat, chat_id, thread_id) -> str:
    if not thread_id or chat is None:
        return ""
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{thread_id}"
    if chat_id:
        return f"https://t.me/c/{_internal_id(chat_id)}/{thread_id}"
    return ""


def _build_message_deep_link(chat, chat_id, message_id) -> str:
    from urllib.parse import quote

    if not message_id or chat is None:
        return ""
    username = getattr(chat, "username", None)
    if username:
        return f"tg://resolve?domain={quote(str(username))}&post={quote(str(message_id))}"
    if chat_id:
        return f"tg://privatepost?channel={quote(_internal_id(chat_id))}&post={quote(str(message_id))}"
    return ""


# ---------------------------------------------------------------------------
# Error hints (port of getErrorHint)
# ---------------------------------------------------------------------------
def _error_hint(err) -> str:
    if not err:
        return ""
    msg = str(getattr(err, "message", None) or err)
    if "ECONNREFUSED" in msg or "ENOTFOUND" in msg:
        return " (lỗi kết nối mạng)"
    if "401" in msg or "403" in msg or "PERMISSION_DENIED" in msg:
        return " (không có quyền truy cập sheet)"
    if "404" in msg or "NOT_FOUND" in msg:
        return " (sheet không tồn tại)"
    if "QUOTA_EXCEEDED" in msg:
        return " (vượt quota Google API)"
    return ""


async def _send(client, chat_id, text, thread_id=None):
    kwargs = {}
    if thread_id:
        kwargs["reply_to"] = thread_id
    await client.send_message(chat_id, text, **kwargs)


async def _handle_error(client, chat_id, user_msg, err, thread_id=None):
    hint = _error_hint(err)
    log.error("%s: %s", user_msg, err)
    await _send(client, chat_id, f"{user_msg}{hint}.", thread_id)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
async def _on_message(event):
    client = event.client
    message = event.message
    raw_text = (message.text or "").strip()
    text = raw_text.lower()
    product_code = normalize_product_code(raw_text)

    chat = await event.get_chat()
    chat_id = event.chat_id
    is_private = bool(event.is_private)
    is_group = bool(event.is_group)
    thread_id = _thread_id(message)
    message_id = message.id

    thread_url = _build_thread_url(chat, chat_id, thread_id)
    # reply thread (topic) preserved when present, matching options.message_thread_id
    reply_thread = thread_id if thread_id else None

    is_quoted = raw_text.startswith('"') and raw_text.endswith('"') and len(raw_text) >= 2

    # 1) private /start <messageId>
    if is_private:
        start_match = re.match(r"^/start(?:\s+([^\s]+))?$", raw_text, re.I)
        if start_match:
            lookup_id = (start_match.group(1) or "").strip()
            if not lookup_id:
                await _send(client, chat_id, "Thiếu mã lô hàng.", reply_thread)
                return
            try:
                row_values = await _manager.lookup_import_row_by_message_id(lookup_id)
                if not row_values:
                    await _send(client, chat_id, "Không tìm thấy lô hàng.", reply_thread)
                    return
                out = format_import_row_message(row_values)
                await _send(
                    client,
                    chat_id,
                    out or "Không tìm thấy dữ liệu lô hàng.",
                    reply_thread,
                )
            except Exception as err:  # noqa: BLE001
                await _handle_error(client, chat_id, "Tra cứu lô hàng thất bại", err, reply_thread)
            return

    # 2) quoted payload -> append rows
    if is_quoted:
        rows = parse_quoted_payload(raw_text)
        if not rows:
            await _send(client, chat_id, "Không tìm thấy dữ liệu trong đoạn trích.", reply_thread)
            return
        try:
            result = await _manager.append_rows(rows, thread_url)
            suffix = " (đã ghi đè các dòng cũ trong chủ đề này)" if result and result.get("replaced") else ""
            await _send(client, chat_id, f"Đã thêm {len(rows)} dòng vào sheet{suffix}.", reply_thread)
        except Exception as err:  # noqa: BLE001
            await _handle_error(client, chat_id, "Thêm dữ liệu vào sheet thất bại", err, reply_thread)
        return

    # 3) group + leading amount -> import row
    amount_payload = parse_leading_amount(raw_text)
    if is_group and amount_payload:
        if not thread_id:
            await _send(client, chat_id, "Không tìm thấy mã phiếu sản xuất.", reply_thread)
            return
        try:
            production_info = await _manager.lookup_production_by_thread_id(str(thread_id))
            if not production_info or not production_info.get("productCode"):
                await _send(client, chat_id, "Không tìm thấy mã sản phẩm cho phiếu này.", reply_thread)
                return
            msg_ctx = {
                "date": message.date,
                "sender_name": _format_sender_name(await event.get_sender()),
                "message_id": message_id,
                "message_thread_id": thread_id,
                "message_deep_link": _build_message_deep_link(chat, chat_id, message_id),
            }
            await _manager.append_import_row(msg_ctx, amount_payload, production_info)
        except Exception as err:  # noqa: BLE001
            await _handle_error(client, chat_id, "Ghi dữ liệu vào sheet thất bại", err, reply_thread)
        return

    # 4) group + product-code candidate -> topic row (allowed products)
    is_product_candidate = (
        len(product_code) > 0
        and re.match(r"^[a-z0-9]+$", product_code) is not None
        and re.search(r"\d", product_code) is not None
    )
    if is_group and is_product_candidate:
        try:
            allowed = await _manager.is_allowed_product_code(product_code)
            if not allowed:
                return
            msg_ctx = {
                "date": message.date,
                "sender_name": _format_sender_name(await event.get_sender()),
                "message_thread_id": thread_id,
            }
            result = await _manager.append_topic_row(msg_ctx, thread_url, product_code)
            if result and result.get("skipped") == "duplicate":
                return
            if result and result.get("skipped") in ("missing_thread_url", "missing_thread_id"):
                await _send(client, chat_id, "Không tìm thấy liên kết chủ đề.", reply_thread)
        except Exception as err:  # noqa: BLE001
            await _handle_error(client, chat_id, "Ghi dữ liệu vào sheet thất bại", err, reply_thread)
        return

    # 5) get/file DDMMYYYY -> export HTML
    get_match = re.match(r"^get\s+(\d{8})$", raw_text, re.I)
    file_match = re.match(r"^file\s+(\d{8})$", raw_text, re.I)
    match = get_match or file_match
    if match:
        compact_date = match.group(1)
        sheet_name = format_sheet_name_from_compact_date(compact_date)
        if not sheet_name:
            await _send(client, chat_id, "Sai định dạng ngày. Dùng DDMMYYYY.", reply_thread)
            return
        try:
            sheet = await _manager.find_sheet_by_name(sheet_name)
            if not sheet:
                await _send(client, chat_id, f"Không tìm thấy sheet {sheet_name}.", reply_thread)
                return
            values = trim_trailing_empty_rows(await _manager.get_sheet_values(sheet_name))
            filtered = filter_export_columns(values)
            if not filtered:
                await _send(client, chat_id, f"Sheet {sheet_name} trống.", reply_thread)
                return
            html = build_html(sheet_name, filtered)
            safe_name = re.sub(r"[\\/]", "-", sheet_name)
            file_path = os.path.join(tempfile.gettempdir(), f"{safe_name}.html")
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            try:
                await client.send_file(
                    chat_id,
                    file_path,
                    caption=f"Sheet {sheet_name}",
                    reply_to=reply_thread,
                    force_document=True,
                )
            finally:
                try:
                    os.unlink(file_path)
                except OSError:
                    pass
        except Exception as err:  # noqa: BLE001
            await _handle_error(client, chat_id, "Xuất file thất bại", err, reply_thread)
        return

    # 6) "hi" -> greeting (to sender's private chat when not already private)
    if text == "hi":
        target = chat_id if is_private else (getattr(message, "sender_id", None) or chat_id)
        # drop topic thread when target differs from the source chat
        t = reply_thread if target == chat_id else None
        await _send(client, target, "xin chào", t)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def start_sheets_bot(api_id, api_hash):
    """Start the sheets bot. Returns the TelegramClient, or None if unconfigured."""
    global _client, _manager

    token = config.bot_token()
    if not token or config._is_placeholder(token):
        log.warning("SHEETS_BOT_TOKEN/TELEGRAM_BOT_TOKEN not set — sheets bot skipped")
        return None
    if not config.has_credentials():
        log.warning(
            "Google credentials not configured "
            "(GOOGLE_APPLICATION_CREDENTIALS[_JSON|_B64]) — sheets bot skipped"
        )
        return None

    from .sheets import SheetsManager

    _manager = SheetsManager()

    _client = TelegramClient("sheets_bot_session", api_id, api_hash)
    await _client.start(bot_token=token)
    me = await _client.get_me()
    log.info("Sheets bot started as @%s (id=%s)", getattr(me, "username", None), me.id)

    _client.add_event_handler(_on_message, events.NewMessage(incoming=True))

    # Startup: migrate existing managed sheets to latest header layout.
    try:
        await _manager.migrate_existing_managed_sheets()
        log.info("Managed sheet header migration completed.")
    except Exception as err:  # noqa: BLE001
        log.error("Failed to migrate existing managed sheets: %s", err)

    return _client


def get_manager():
    return _manager
