"""Production (sản xuất) group bot — ported from node bots/productionOrders.js.

SQLite-native (production_store). Scope: group command handlers, simple
per-slip inventory (numeric add → slip total), google-sheet CSV report, and
channel-post → auto-create forum topic. Excludes cross-group kho / material
warehouse side-effects and web routes.
"""
from __future__ import annotations

import json
import logging
import os
import random
import sqlite3
from datetime import datetime, timezone, timedelta

from telethon import events
from telethon.tl.types import MessageService
from telethon.tl.functions.messages import CreateForumTopicRequest

from bot_core.config import (
    PRODUCTION_GROUP_ID,
    PRODUCTION_CHANNEL_ID,
    SP_INFO,
    CAY_TRONG_1_CHAO,
    PRODUCT_CODES,
    is_admin,
)
from production_store import (
    create_production_table,
    migrate_production_table,
    get_slip,
    upsert_slip,
    set_sp,
    set_target,
    add_number,
    set_total,
    set_bang,
    delete_slip,
)
from production_store.domain import looks_like_report, parse_report, compute_report

from .thread_utils import extract_thread_id

log = logging.getLogger("production")
from utils.paths import SHARED_DB_PATH
from utils.db import get_connection


def _emit_prod(thread_id=None):
    """Đẩy realtime cho webapp (list + dashboard SX) sau mutation từ Telegram —
    best-effort; không có loop/aiohttp (script, test) thì im lặng bỏ qua.
    thread_id=None → productions_changed (tạo/xoá phiếu), có → production_changed."""
    try:
        from server_app.realtime import emit_production_changed, emit_productions_changed
        if thread_id is None:
            emit_productions_changed()
        else:
            emit_production_changed(thread_id)
    except Exception:  # noqa: BLE001
        pass
# Base URL của webapp (Tailscale/LAN). Trống = chưa cấu hình → chỉ dùng link topic
# Telegram (luôn hoạt động). Đặt WEBAPP_URL để hiện link web /app/#/san_xuat/<id>.
# (Bỏ railway finaltelegram — không dùng nữa.)
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")
_VN_TZ = timezone(timedelta(hours=7))


def _conn():
    return get_connection()


# ─── number formatting (node `so()` = toLocaleString('vi-VN')) ──────────────
def _so(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n.is_integer():
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_num(n) -> str:
    n = float(n)
    return str(int(n)) if n.is_integer() else f"{n:.2f}"


def _is_product_code(s: str) -> bool:
    return s in SP_INFO or s in PRODUCT_CODES


def _topic_link(thread_id) -> str:
    """Deep-link tới topic chat của phiếu trong group SX (t.me/c/<internal>/<topic>)."""
    gid = str(PRODUCTION_GROUP_ID)
    internal = gid[4:] if gid.startswith("-100") else gid.lstrip("-")
    return f"https://t.me/c/{internal}/{thread_id}"


def _web_link(thread_id) -> str | None:
    """Link webapp xem phiếu, hoặc None nếu chưa cấu hình WEBAPP_URL."""
    return f"{WEBAPP_URL}/app/#/san_xuat/{thread_id}" if WEBAPP_URL else None


async def _sender_name(msg) -> str:
    """Tên người gửi tin (để ghi vào lần nhập số lượng). Best-effort."""
    try:
        s = await msg.get_sender()
        return (getattr(s, "first_name", None) or getattr(s, "title", None)
                or getattr(s, "username", None) or "")
    except Exception:  # noqa: BLE001
        return ""


async def _send_link_buttons(thread_id) -> None:
    """Gửi nút bấm inline (URL) vào channel qua BOT — tài khoản user KHÔNG gắn được
    inline keyboard (giới hạn Telegram). Best-effort: chưa có bot / bot không phải
    admin channel → bỏ qua, link chữ trong bài channel vẫn còn."""
    from server_app.bot_bootstrap import get_bot_client
    bot = get_bot_client()
    if bot is None:
        return
    from telethon import Button
    row = [Button.url("💬 Mở topic", _topic_link(thread_id))]
    web = _web_link(thread_id)
    if web:
        row.append(Button.url("🔗 Xem phiếu", web))
    buttons = [row]
    try:
        await bot.send_message(PRODUCTION_CHANNEL_ID, "🔖 Phiếu sản xuất", buttons=buttons)
    except Exception as e:  # noqa: BLE001 — cần bot là admin channel; không có thì thôi
        log.warning("bot link-buttons failed thread=%s: %s", thread_id, e)


# CSV parsing moved to production_store/domain.py (parse_report/compute_report/
# looks_like_report) — shared with the webapp endpoint so the two never drift.


# ─── channel message edit (node updateTinNhan, no inline kb on user acct) ───
async def _update_tin_nhan(client, conn, thread_id):
    slip = get_slip(conn, thread_id)
    if not slip:
        return
    channel_id, message_id = slip.get("channel_id"), slip.get("message_id")
    if not channel_id or not message_id:
        return
    text = (
        f"📦 SP: {slip.get('sp_name') or 'Chưa có SP'}"
        f"\n🎯 SX: {slip.get('sx_target') if slip.get('sx_target') is not None else 'Chưa có'}"
        f"\n✅ Nhận: {_so(slip.get('total') or 0)}"
        f"\n💬 Topic: {_topic_link(thread_id)}"
    )
    web = _web_link(thread_id)
    if web:
        text += f"\n🔗 Web: {web}"
    try:
        await client.edit_message(int(channel_id), int(message_id), text)
    except Exception as e:  # noqa: BLE001 — edit is best-effort (unchanged text, perms)
        log.debug("update_tin_nhan edit failed thread=%s: %s", thread_id, e)


async def _create_forum_topic(client, chat_id: int, title: str) -> int | None:
    try:
        result = await client(CreateForumTopicRequest(
            peer=chat_id, title=title, random_id=random.randrange(-2**63, 2**63),
        ))
        for upd in getattr(result, "updates", []) or []:
            m = getattr(upd, "message", None)
            if m is not None and getattr(m, "id", None):
                return m.id
    except Exception as e:  # noqa: BLE001
        log.error("create_forum_topic failed: %s", e)
    return None


HELP_TEXT = """*DANH SÁCH LỆNH TRONG GROUP SẢN XUẤT*

*Quản lý phiếu sản xuất:*
- `<mã sản phẩm>`: Cập nhật sản phẩm cho phiếu.
- `SX <số lượng>`: Cập nhật mục tiêu sản xuất.
- `<số lượng> [ghi chú]`: Nhập số lượng sản phẩm đã nhận.
- `done all tasks`: Tự động hoàn thành số lượng còn lại theo mục tiêu.
- `DEL`: Xóa phiếu sản xuất (chỉ admin).
- `getjson`: Xem dữ liệu JSON của phiếu sản xuất.
- `link` hoặc `/link`: Gửi link xem phiếu trên web.

*Báo cáo sản xuất:*
- Dán dữ liệu CSV từ Google Sheet để nhận báo cáo tổng hợp."""


def register_production_commands(client):
    conn = _conn()
    create_production_table(conn)
    migrate_production_table(conn)
    log.info("production handler listening on group %d, channel %d. DB: %s",
             PRODUCTION_GROUP_ID, PRODUCTION_CHANNEL_ID, SHARED_DB_PATH)

    async def reply(msg, text, parse_mode=None):
        await client.send_message(msg.chat_id, text, reply_to=msg.id, parse_mode=parse_mode)

    # ─── channel post → auto-create forum topic + phiếu ─────────────────────
    @client.on(events.NewMessage(chats=PRODUCTION_CHANNEL_ID))
    async def on_channel_post(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        now = datetime.now(_VN_TZ)
        date_code = now.strftime("%Y%m%d%H%M%S")
        thread_id = await _create_forum_topic(client, PRODUCTION_GROUP_ID, date_code)
        if not thread_id:
            log.error("could not create topic for channel post %d", msg.id)
            return
        upsert_slip(
            conn, thread_id,
            channel_id=PRODUCTION_CHANNEL_ID, message_id=msg.id,
            date=now.strftime("%d/%m/%Y %H:%M"), date_code=date_code,
            text=(msg.text or ""),
        )
        _emit_prod()  # phiếu mới → dashboard webapp refetch
        web = _web_link(thread_id)
        if web:
            try:
                await client.send_message(
                    PRODUCTION_GROUP_ID, f"🔗 Link phiếu trên web: {web}", reply_to=thread_id,
                )
            except Exception as e:  # noqa: BLE001
                log.error("failed to send welcome to topic %s: %s", thread_id, e)
        # Sửa chính bài trong channel để hiện tóm tắt + link (trước đây chỉ gửi vào
        # topic group, bài channel không được cập nhật → không thấy link).
        await _update_tin_nhan(client, conn, thread_id)
        # Nút bấm inline (qua bot) — user account không gắn keyboard được.
        await _send_link_buttons(thread_id)

    # ─── group messages ─────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=PRODUCTION_GROUP_ID))
    async def on_group_msg(event):
        msg = event.message
        if isinstance(msg, MessageService) or not msg.text:
            return
        text = msg.text
        t = text.strip()
        low = t.lower()
        thread_id = extract_thread_id(msg)

        # help
        if low == "?":
            await reply(msg, HELP_TEXT, parse_mode="md")
            return

        # getjson
        if low == "getjson":
            if not thread_id:
                await reply(msg, "❌ Không thể xác định thread ID")
                return
            slip = get_slip(conn, thread_id)
            if not slip:
                await reply(msg, "❌ Không tìm thấy dữ liệu cho thread này")
                return
            dump = json.dumps(slip, ensure_ascii=False, indent=2)
            for i in range(0, len(dump), 4000):
                await reply(msg, f"```\n{dump[i:i + 4000]}\n```", parse_mode="md")
            return

        # link / url
        if low in ("link", "/link", "url", "/url"):
            if not thread_id:
                await reply(msg, "❌ Không xác định được thread hiện tại")
                return
            web = _web_link(thread_id)
            out = f"💬 Topic: {_topic_link(thread_id)}"
            if web:
                out += f"\n🔗 Web: {web}"
            await reply(msg, out)
            return

        # google-sheet CSV → báo cáo sản xuất
        if looks_like_report(text):
            await _handle_csv_report(msg, text, thread_id)
            return

        if not thread_id:
            return  # remaining commands operate on a slip
        slip = get_slip(conn, thread_id)
        processed = t.replace('"', "")
        upper = processed.upper()

        # detailed production qty (*...~)
        if processed.startswith("*"):
            await _handle_detailed(msg, processed, slip)
            return

        # product code update
        if _is_product_code(upper):
            info = SP_INFO.get(upper, {})
            set_sp(conn, thread_id, upper, info.get("mam"), info.get("luong"))
            _emit_prod(thread_id)
            out = f"Cập nhật sp thành {upper}"
            if upper in CAY_TRONG_1_CHAO:
                out += f"\n🌿 Cây trong 1 chảo: {CAY_TRONG_1_CHAO[upper]}"
            await reply(msg, out)
            await _update_tin_nhan(client, conn, thread_id)
            return

        # SX target
        if upper.startswith("SX "):
            if not slip or not slip.get("sp_name"):
                await reply(msg, "Chưa có sản phẩm, chưa nhập hàng được")
                return
            try:
                sx = int(processed[3:].strip())
            except ValueError:
                await reply(msg, "❌ Số lượng SX không hợp lệ")
                return
            set_target(conn, thread_id, sx)
            _emit_prod(thread_id)
            await reply(msg, "Cập nhật thành công")
            await _update_tin_nhan(client, conn, thread_id)
            return

        # DEL (admin) — cấm xoá nếu phiếu đã tạo thùng (giống webapp, 1 rule chung)
        if processed == "DEL":
            if is_admin(getattr(msg, "sender_id", None)):
                from inventory_store import count_boxes_by_source
                n = count_boxes_by_source(conn, thread_id)
                if n > 0:
                    await reply(msg, f"❌ Không xoá được — phiếu đã tạo {n} thùng. Xoá các thùng đó trước.")
                    return
                delete_slip(conn, thread_id)
                _emit_prod()  # xoá phiếu → dashboard webapp refetch
                await reply(msg, "Đã xóa phiếu")
            return

        # done all tasks (per-slip)
        if processed.lower() == "done all tasks":
            if not slip or not slip.get("sp_name"):
                await reply(msg, "Chưa có sản phẩm, không thể hoàn thành tất cả nhiệm vụ")
                return
            sx_target = slip.get("sx_target")
            current_total = slip.get("total") or 0
            if not sx_target:
                await reply(msg, "Chưa có mục tiêu sản xuất (SX), không thể hoàn thành tất cả nhiệm vụ")
                return
            if current_total >= sx_target:
                await reply(msg, "Tất cả nhiệm vụ đã hoàn thành rồi!")
                return
            remaining = sx_target - current_total
            add_number(conn, thread_id, remaining, "Hoàn thành tất cả nhiệm vụ", by=await _sender_name(msg))
            set_total(conn, thread_id, sx_target)
            _emit_prod(thread_id)
            await reply(
                msg,
                f"✅ Đã hoàn thành tất cả nhiệm vụ!\n"
                f"Số lượng bổ sung: {_so(remaining)}\nTổng đạt được: {_so(sx_target)}",
            )
            await _update_tin_nhan(client, conn, thread_id)
            return

        # numeric qty add (simple per-slip inventory)
        words = processed.split(" ")
        try:
            amount = float(words[0])
        except ValueError:
            return
        if not slip or not slip.get("sp_name"):
            await reply(msg, "Chưa có sản phẩm, chưa nhập hàng được")
            return
        note = " ".join(words[1:])
        total = add_number(conn, thread_id, amount, note, by=await _sender_name(msg))
        _emit_prod(thread_id)
        await reply(msg, f"Cập nhật số lượng thành công, tổng hiện tại: {_fmt_num(total)}")
        await _update_tin_nhan(client, conn, thread_id)

    async def _handle_detailed(msg, processed, slip):
        so_cay_1_mam = slip.get("sp_mam") if slip else None
        segments = [s for s in processed.replace("*", "").replace("\n", "").split("~") if s]
        real_total = 0.0
        for seg in segments:
            parts = seg.replace(",", ".").split(";")

            def _p(i):
                try:
                    return float(parts[i])
                except (IndexError, ValueError):
                    return 0.0
            gach, tru, le = _p(1), _p(2), _p(3)
            mam_de, sp_de = _p(5), _p(6)
            mam = mam_de if mam_de else gach * 5 - tru - (1 if le > 0 else 0)
            if not so_cay_1_mam:
                await reply(msg, "Chưa nhập sp")
                return
            total = sp_de if sp_de else so_cay_1_mam * mam + le
            real_total += total
        await reply(msg, f"Tổng SX = {_fmt_num(real_total)}")

    async def _handle_csv_report(msg, text, thread_id):
        parsed = parse_report(text)
        if not parsed["rows"]:
            await reply(msg, "❌ Không thể phân tích dữ liệu. Vui lòng dán dữ liệu từ Google Sheet với định dạng đúng.")
            return

        # product code: from the data, else the slip's current sp_name
        product_code = parsed.get("product_code")
        if not product_code and thread_id:
            slip = get_slip(conn, thread_id)
            if slip and slip.get("sp_name"):
                product_code = slip["sp_name"].upper()
        so_cay_1_mam = SP_INFO.get(product_code, {}).get("mam", 0) if product_code else 0

        report = compute_report({**parsed, "product_code": product_code}, so_cay_1_mam)

        out = "📊 **BÁO CÁO SẢN XUẤT**\n"
        if product_code:
            out += f"📦 Mã SP: **{product_code}**\n🌿 Số cây 1 mâm: {so_cay_1_mam}\n"
        else:
            out += "⚠️ _Chưa có mã sản phẩm - sử dụng cột Tổng SP từ dữ liệu_\n"
        out += "\n👷 **Chi tiết theo thợ:**\n"

        maker_totals = sorted(
            ((r["name"], r["tong_calc"]) for r in report["rows"] if r["tong_calc"] > 0),
            key=lambda x: x[1], reverse=True,
        )
        for name, total in maker_totals:
            out += f"• {name}: **{_fmt_num(total)}** SP\n"
        out += f"\n📈 **TỔNG CỘNG: {_fmt_num(report['grand_total'])} SP**"
        if product_code and so_cay_1_mam > 0:
            out += f"\n\n_Công thức: (Số gạch × 5 - Số trừ - Làm tròn) × {so_cay_1_mam} + Số cây lẻ_"

        await reply(msg, out, parse_mode="md")

        if thread_id:
            set_bang(conn, thread_id, {
                "product_code": product_code,
                "so_cay_1_mam": so_cay_1_mam,
                "date": report.get("date"),
                "start": report.get("start"),
                "end": report.get("end"),
                "rows": report["rows"],
                "grand_total": report["grand_total"],
                "updated_at": datetime.now(_VN_TZ).isoformat(),
            })
            _emit_prod(thread_id)  # báo cáo đổi → list card + dashboard SX refetch
