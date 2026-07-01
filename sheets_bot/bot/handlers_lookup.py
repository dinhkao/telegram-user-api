"""Read-side handlers: /start import lookup and get/file HTML export."""

from __future__ import annotations

import os
import re
import tempfile

from ..parse import (
    build_html,
    filter_export_columns,
    format_import_row_message,
    format_sheet_name_from_compact_date,
    trim_trailing_empty_rows,
)
from .reply import handle_error, send


async def handle_start(ctx) -> bool:
    if not ctx.is_private:
        return False
    m = re.match(r"^/start(?:\s+([^\s]+))?$", ctx.raw_text, re.I)
    if not m:
        return False
    lookup_id = (m.group(1) or "").strip()
    if not lookup_id:
        await send(ctx.client, ctx.chat_id, "Thiếu mã lô hàng.", ctx.reply_thread)
        return True
    try:
        row_values = await ctx.manager.lookup_import_row_by_message_id(lookup_id)
        if not row_values:
            await send(ctx.client, ctx.chat_id, "Không tìm thấy lô hàng.", ctx.reply_thread)
            return True
        out = format_import_row_message(row_values)
        await send(ctx.client, ctx.chat_id, out or "Không tìm thấy dữ liệu lô hàng.", ctx.reply_thread)
    except Exception as err:  # noqa: BLE001
        await handle_error(ctx.client, ctx.chat_id, "Tra cứu lô hàng thất bại", err, ctx.reply_thread)
    return True


async def handle_export(ctx) -> bool:
    m = re.match(r"^get\s+(\d{8})$", ctx.raw_text, re.I) or re.match(
        r"^file\s+(\d{8})$", ctx.raw_text, re.I
    )
    if not m:
        return False
    sheet_name = format_sheet_name_from_compact_date(m.group(1))
    if not sheet_name:
        await send(ctx.client, ctx.chat_id, "Sai định dạng ngày. Dùng DDMMYYYY.", ctx.reply_thread)
        return True
    try:
        sheet = await ctx.manager.find_sheet_by_name(sheet_name)
        if not sheet:
            await send(ctx.client, ctx.chat_id, f"Không tìm thấy sheet {sheet_name}.", ctx.reply_thread)
            return True
        values = trim_trailing_empty_rows(await ctx.manager.get_sheet_values(sheet_name))
        filtered = filter_export_columns(values)
        if not filtered:
            await send(ctx.client, ctx.chat_id, f"Sheet {sheet_name} trống.", ctx.reply_thread)
            return True
        safe_name = re.sub(r"[\\/]", "-", sheet_name)
        file_path = os.path.join(tempfile.gettempdir(), f"{safe_name}.html")
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(build_html(sheet_name, filtered))
        try:
            await ctx.client.send_file(
                ctx.chat_id, file_path, caption=f"Sheet {sheet_name}",
                reply_to=ctx.reply_thread, force_document=True,
            )
        finally:
            try:
                os.unlink(file_path)
            except OSError:
                pass
    except Exception as err:  # noqa: BLE001
        await handle_error(ctx.client, ctx.chat_id, "Xuất file thất bại", err, ctx.reply_thread)
    return True
