"""Write-side handlers: quoted rows, group amount/import, topic product, hi."""

from __future__ import annotations

import re

from ..parse import parse_leading_amount, parse_quoted_payload
from .reply import handle_error, send


async def handle_quoted(ctx) -> bool:
    if not ctx.is_quoted:
        return False
    rows = parse_quoted_payload(ctx.raw_text)
    if not rows:
        await send(ctx.client, ctx.chat_id, "Không tìm thấy dữ liệu trong đoạn trích.", ctx.reply_thread)
        return True
    try:
        result = await ctx.manager.append_rows(rows, ctx.thread_url)
        suffix = " (đã ghi đè các dòng cũ trong chủ đề này)" if result and result.get("replaced") else ""
        await send(ctx.client, ctx.chat_id, f"Đã thêm {len(rows)} dòng vào sheet{suffix}.", ctx.reply_thread)
    except Exception as err:  # noqa: BLE001
        await handle_error(ctx.client, ctx.chat_id, "Thêm dữ liệu vào sheet thất bại", err, ctx.reply_thread)
    return True


async def handle_amount(ctx) -> bool:
    amount = parse_leading_amount(ctx.raw_text)
    if not (ctx.is_group and amount):
        return False
    if not ctx.thread_id:
        await send(ctx.client, ctx.chat_id, "Không tìm thấy mã phiếu sản xuất.", ctx.reply_thread)
        return True
    try:
        info = await ctx.manager.lookup_production_by_thread_id(str(ctx.thread_id))
        if not info or not info.get("productCode"):
            await send(ctx.client, ctx.chat_id, "Không tìm thấy mã sản phẩm cho phiếu này.", ctx.reply_thread)
            return True
        msg = {
            "date": ctx.message.date,
            "sender_name": await ctx.sender_name(),
            "message_id": ctx.message_id,
            "message_thread_id": ctx.thread_id,
            "message_deep_link": ctx.deep_link(),
        }
        await ctx.manager.append_import_row(msg, amount, info)
    except Exception as err:  # noqa: BLE001
        await handle_error(ctx.client, ctx.chat_id, "Ghi dữ liệu vào sheet thất bại", err, ctx.reply_thread)
    return True


async def handle_product(ctx) -> bool:
    code = ctx.product_code
    candidate = bool(code) and re.match(r"^[a-z0-9]+$", code) and re.search(r"\d", code)
    if not (ctx.is_group and candidate):
        return False
    try:
        if not await ctx.manager.is_allowed_product_code(code):
            return True
        msg = {
            "date": ctx.message.date,
            "sender_name": await ctx.sender_name(),
            "message_thread_id": ctx.thread_id,
        }
        result = await ctx.manager.append_topic_row(msg, ctx.thread_url, code)
        if result and result.get("skipped") == "duplicate":
            return True
        if result and result.get("skipped") in ("missing_thread_url", "missing_thread_id"):
            await send(ctx.client, ctx.chat_id, "Không tìm thấy liên kết chủ đề.", ctx.reply_thread)
    except Exception as err:  # noqa: BLE001
        await handle_error(ctx.client, ctx.chat_id, "Ghi dữ liệu vào sheet thất bại", err, ctx.reply_thread)
    return True


async def handle_hi(ctx) -> bool:
    if ctx.text != "hi":
        return False
    target = ctx.chat_id if ctx.is_private else (getattr(ctx.message, "sender_id", None) or ctx.chat_id)
    thread = ctx.reply_thread if target == ctx.chat_id else None
    await send(ctx.client, target, "xin chào", thread)
    return True
