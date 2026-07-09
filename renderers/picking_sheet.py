from __future__ import annotations

import logging
import os
import tempfile

from printouts.common import queue_html_for_print
from renderers.common import esc, internal_group_id, qr_url, vn_now

log = logging.getLogger("picking_sheet")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
CHANNEL_DON_HANG_MOI = int(os.getenv("CHANNEL_DON_HANG_MOI", "-1002138495144"))
PICKING_PRINT_PATH = "meta/to_print2"


def generate_picking_sheet_html(thread_id: int, order_text: str, invoice: list[dict] | None = None, channel_id: int | None = None, message_id: int | None = None, add_fix_banner: bool = False, manual_print_note: str | None = None) -> str:
    order_topic_url = f"tg://privatepost?channel={internal_group_id(ORDER_GROUP_ID)}&post={thread_id}"
    qr_target = f"tg://privatepost?channel={internal_group_id(channel_id)}&post={message_id}" if channel_id and message_id else order_topic_url
    qr_size = 120
    qr_link = qr_url(qr_target, qr_size)
    product_rows = "".join(
        f"""<tr>
              <td class="stt">{idx + 1}</td>
              <td class="product-name">{esc(it.get("sp", it.get("name", it.get("productName", "Sản phẩm"))))}</td>
              <td class="so-luong">{it.get("sl", it.get("quantity", 0))}</td>
            </tr>"""
        for idx, it in enumerate(invoice or [])
    )
    now_str = vn_now().strftime("%H:%M:%S %d/%m/%Y")
    fix_banner = '<div class="banner">Đơn hàng được sửa đổi. Hủy phiếu soạn hàng cũ</div>' if add_fix_banner else ""
    manual_note = f'<div class="manual-note">{esc(manual_print_note)}</div>' if manual_print_note else ""
    safe_text = esc(order_text or "")
    safe_id = esc(str(thread_id))
    qr_img = f'<img src="{qr_link}" alt="QR tới đơn hàng" width="{qr_size}" height="{qr_size}" />'
    html = (
        f'<!DOCTYPE html><html lang="vi"><head>\n<meta charset="UTF-8" />\n<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n<title>PHIẾU SOẠN HÀNG</title>\n<style>\n  body {{ width: 280px; font-family: Arial, sans-serif; }}\n  .stt {{ width: 20px; text-align: center; }}\n  .invoice-hd {{ text-align: center; font-weight: bold; }}\n  .so-luong {{ text-align: center; font-size: 18px; }}\n  .product-name {{ font-size: 18px; font-weight: bold; }}\n  table {{ width: 100%; border-collapse: collapse; }}\n  td, th {{ padding: 2px; font-size: 14px; vertical-align: middle; }}\n  .hr {{ margin: 5px auto; border: 0; border-top: 1px solid #000; }}\n  .title {{ text-align:center; font-weight:bold; }}\n  .order-text {{ white-space: pre-wrap; font-size: 20px; }}\n  .order-id {{ font-weight: bold; font-size: 16px; }}\n  .header {{ width:100%; }}\n  .right {{ text-align:right; }}\n  .align-top {{ vertical-align: top; }}\n  .qrbox {{ text-align:right; vertical-align:top; }}\n  .muted {{ color:#333; }}\n  .banner {{ margin-bottom: 6px; font-weight: bold; color: #c00; }}\n  .strike {{ text-decoration: line-through; }}\n  .manual-note {{ margin-bottom: 6px; font-weight: bold; }}\n</style>\n</head><body>\n  {manual_note}\n  {fix_banner}\n  <table class="header" border="0">\n    <tr>\n      <td class="align-top">\n        <div class="title">PHIẾU SOẠN HÀNG</div>\n        <div>{now_str}</div>\n      </td>\n      <td class="qrbox">\n        {qr_img}\n      </td>\n    </tr>\n  </table>\n  <hr class="hr" />\n  <div class="order-id">Mã đơn: {safe_id}</div>\n  <div class="muted">Đơn: </div>\n  <div class="order-text">{safe_text}</div>\n  <hr class="hr" />\n  <table border="1">\n    <tr>\n      <th class="stt"></th>\n      <th class="invoice-hd">Sản phẩm</th>\n      <th class="invoice-hd">SL</th>\n    </tr>\n    {product_rows}\n  </table>\n</body></html>'
    )
    return html


async def _enqueue_picking_html_for_print(html: str, copies: int = 1) -> bool:
    from firebase_png_print import ref as fb_ref
    ref = fb_ref(PICKING_PRINT_PATH)
    if ref is None:
        log.warning("Firebase not configured — skipping picking sheet print queue")
        return False
    try:
        ok = await queue_html_for_print(ref, html, copies)
        if ok:
            log.info("Queued %d picking sheet copy(ies) for printing", max(1, copies))
        return ok
    except Exception as e:
        log.warning("Failed to queue picking sheet for printing: %s", e)
        return False


async def generate_picking_sheet(client, conn, thread_id: int) -> bool:
    try:
        from order_db import get_order_by_thread_id
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            log.warning("picking_sheet: order not found thread=%d", thread_id)
            return False
        from order_store.display import resolve_invoice_display
        html = generate_picking_sheet_html(thread_id, order.get("text", ""),
                                           resolve_invoice_display(order.get("invoice") or [], conn),
                                           order.get("channel_id"), order.get("message_id"))
        try:
            await _enqueue_picking_html_for_print(html)
            await client.send_message(ORDER_GROUP_ID, "🖨️ Đã gửi lệnh in phiếu soạn hàng", reply_to=thread_id, link_preview=False)
        except Exception as e:
            log.warning("Print queue / notification failed for thread=%d: %s", thread_id, e)
        try:
            file_path = os.path.join(tempfile.gettempdir(), f"phieu_soan_{thread_id}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)
            await client.send_file(ORDER_GROUP_ID, file_path, reply_to=thread_id, force_document=True)
            try:
                os.unlink(file_path)
            except Exception:
                pass
        except Exception as e:
            log.warning("Failed to send picking sheet file for thread=%d: %s", thread_id, e)
        log.info("Generated picking sheet for thread=%d", thread_id)
        return True
    except Exception as e:
        log.error("Error generating picking sheet for thread=%d: %s", thread_id, e)
        try:
            await client.send_message(ORDER_GROUP_ID, "❌ Lỗi khi tạo phiếu soạn hàng", reply_to=thread_id)
        except Exception:
            pass
        return False
