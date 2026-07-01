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

from .thread_utils import extract_thread_id

log = logging.getLogger("production")
from utils.paths import SHARED_DB_PATH
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://finaltelegram-production.up.railway.app").rstrip("/")
_VN_TZ = timezone(timedelta(hours=7))


def _conn():
    conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


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


# ─── CSV parsing (node parseSanXuatData / parseCSVLine) ─────────────────────
def _parse_csv_line(line: str) -> list[str]:
    cells, current, in_quotes = [], "", False
    i = 0
    while i < len(line):
        ch = line[i]
        nxt = line[i + 1] if i + 1 < len(line) else ""
        if ch == '"':
            if in_quotes and nxt == '"':
                current += '"'
                i += 1
            else:
                in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            cells.append(current)
            current = ""
        else:
            current += ch
        i += 1
    cells.append(current)
    out = []
    for cell in cells:
        if cell.startswith('"') and cell.endswith('"'):
            out.append(cell[1:-1].replace('""', '"'))
        else:
            out.append(cell)
    return out


def _clean_num(val) -> float:
    if val is None or val in ('""', ""):
        return 0.0
    cleaned = str(val).strip().strip('"').strip("'").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _is_nan_cell(val: str) -> bool:
    try:
        float(str(val).strip().strip('"'))
        return False
    except ValueError:
        return True


def parse_san_xuat_data(text: str) -> list[dict]:
    lines = text.strip().split("\n")
    if not lines:
        return []
    delimiter = "\t" if "\t" in lines[0] else ","
    parsed = []
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        cells = _parse_csv_line(line) if delimiter == "," else line.split(delimiter)
        cells = [c.strip() for c in cells]
        if idx == 0 and (
            "thợ" in (cells[0] or "").lower()
            or (len(cells) > 1 and _is_nan_cell(cells[1]))
            or (len(cells) > 2 and _is_nan_cell(cells[2]))
        ):
            continue  # header row
        if len(cells) >= 4:
            parsed.append({
                "name": cells[0].strip().strip('"').strip("'"),
                "so_gach": _clean_num(cells[1]),
                "so_tru": _clean_num(cells[2]),
                "so_cay_le": _clean_num(cells[3]),
                "tong_sp": _clean_num(cells[4]) if len(cells) > 4 else 0.0,
            })
    return parsed


def _looks_like_csv(text: str) -> bool:
    low = text.lower()
    return (
        '"thợ"' in low
        or ('","' in text and len(text.split("\n")) > 3)
        or "thợ,số gạch" in low
    )


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
    )
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
        link = f"{PUBLIC_URL}/san_xuat/{thread_id}"
        try:
            await client.send_message(
                PRODUCTION_GROUP_ID, f"🔗 Link phiếu trên web: {link}", reply_to=thread_id,
            )
        except Exception as e:  # noqa: BLE001
            log.error("failed to send welcome to topic %s: %s", thread_id, e)

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
            link = f"{PUBLIC_URL}/san_xuat/{thread_id}"
            await reply(msg, f"🔗 Link phiếu trên web: {link}")
            return

        # google-sheet CSV → báo cáo sản xuất
        if _looks_like_csv(text):
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
            await reply(msg, "Cập nhật thành công")
            await _update_tin_nhan(client, conn, thread_id)
            return

        # DEL (admin)
        if processed == "DEL":
            if is_admin(getattr(msg, "sender_id", None)):
                delete_slip(conn, thread_id)
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
            add_number(conn, thread_id, remaining, "Hoàn thành tất cả nhiệm vụ")
            set_total(conn, thread_id, sx_target)
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
        total = add_number(conn, thread_id, amount, note)
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
        product_code = None
        for line in text.split("\n"):
            up = line.upper().strip()
            if up.startswith("SP:") or up.startswith("MÃ SP:"):
                product_code = up.split(":", 1)[1].strip()
                break
            if up in SP_INFO:
                product_code = up
                break
        if not product_code and thread_id:
            slip = get_slip(conn, thread_id)
            if slip and slip.get("sp_name"):
                product_code = slip["sp_name"].upper()

        rows = parse_san_xuat_data(text)
        if not rows:
            await reply(msg, "❌ Không thể phân tích dữ liệu. Vui lòng dán dữ liệu từ Google Sheet với định dạng đúng.")
            return

        so_cay_1_mam = SP_INFO.get(product_code, {}).get("mam", 0) if product_code else 0
        out = "📊 **BÁO CÁO SẢN XUẤT**\n"
        if product_code:
            out += f"📦 Mã SP: **{product_code}**\n🌿 Số cây 1 mâm: {so_cay_1_mam}\n"
        else:
            out += "⚠️ _Chưa có mã sản phẩm - sử dụng cột Tổng SP từ dữ liệu_\n"
        out += "\n👷 **Chi tiết theo thợ:**\n"

        grand_total = 0.0
        maker_totals = []
        table_rows = []
        for row in rows:
            gach, tru, le, tong = row["so_gach"], row["so_tru"], row["so_cay_le"], row["tong_sp"]
            if not gach and not tru and not le and not tong:
                continue
            if so_cay_1_mam > 0:
                so_mam = max(gach * 5 - tru - (1 if le > 0 else 0), 0)
                total = so_cay_1_mam * so_mam + le
            else:
                total = tong
            total = round(total * 100) / 100
            if total > 0:
                maker_totals.append((row["name"], total))
                grand_total += total
            table_rows.append({**row, "tong_calc": total})

        maker_totals.sort(key=lambda x: x[1], reverse=True)
        for name, total in maker_totals:
            out += f"• {name}: **{_fmt_num(total)}** SP\n"
        grand_total = round(grand_total * 100) / 100
        out += f"\n📈 **TỔNG CỘNG: {_fmt_num(grand_total)} SP**"
        if product_code and so_cay_1_mam > 0:
            out += f"\n\n_Công thức: (Số gạch × 5 - Số trừ - Làm tròn) × {so_cay_1_mam} + Số cây lẻ_"

        await reply(msg, out, parse_mode="md")

        if thread_id:
            set_bang(conn, thread_id, {
                "product_code": product_code,
                "so_cay_1_mam": so_cay_1_mam,
                "rows": table_rows,
                "grand_total": grand_total,
                "updated_at": datetime.now(_VN_TZ).isoformat(),
            })
