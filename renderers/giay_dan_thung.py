"""HTML GIẤY DÁN THÙNG (nhãn dán lên thùng hàng gửi xe) — in trên MÁY IN NHIỆT 80mm
qua cùng hàng đợi hoá đơn (Firebase `meta/to_print`, printouts/common).

Khổ: rộng 280px (= bề rộng in được của hoá đơn KiotViet, KHÔNG dùng 80mm vì vùng
in thật của driver hẹp hơn 80mm — hoá đơn 280px là số đã chứng minh), dài ≤ 297mm
(1080px ≈ 286mm, chừa lề để không tràn sang trang 2 nếu driver đặt trang cố định
80×297). Chữ XOAY DỌC (`writing-mode: vertical-rl`) để dán dọc theo cạnh thùng —
đọc theo chiều dài giấy. Dòng dài tự HẠ CỠ CHỮ (`fit_font_px`) thay vì cắt cụt.
Không tài nguyên ngoài (ảnh/font) — máy in không cần mạng.
"""
from __future__ import annotations

import base64
import os

from renderers.common import esc

GDT_SENDER = os.getenv("GDT_SENDER", "Kẹo Lê Trang 0941 586 542")

LABEL_W = 280          # px — bằng bề rộng hoá đơn nhiệt
LABEL_H = 1080         # px ≈ 286mm (< 297mm)
TAIL_MARK = "\u2003" * 5 + "."   # ≈ 5 em trống + "." ở cuối dòng người nhận
SIDE_PAD = 30          # px chừa 2 cạnh dài (dòng chữ không ra sát mép — chỗ dán keo)
FONT_MAX = 40
FONT_MIN = 16
_CHAR_EM = 0.62        # bề rộng TB 1 ký tự Arial đậm (tính theo em) — ước lượng an toàn


def fit_font_px(text: str, max_px: int = LABEL_H - 40, font_max: int = FONT_MAX, font_min: int = FONT_MIN) -> int:
    """Cỡ chữ lớn nhất (≤ font_max) để `text` nằm gọn trong `max_px` theo chiều dài
    giấy; không nhỏ hơn font_min (dòng quá dài thì chấp nhận tràn thay vì chữ li ti)."""
    n = len(text or "")
    if n <= 0:
        return font_max
    fit = int(max_px / (_CHAR_EM * n))
    return max(font_min, min(font_max, fit))


def label_lines(gdt: dict, sender: str | None = None) -> list[str]:
    """4 dòng chữ trên nhãn theo mẫu cũ; dòng ghi chú rỗng thì bỏ."""
    sender = sender if sender is not None else GDT_SENDER
    ten = str(gdt.get("ten_gdt") or "").strip()
    sdt = str(gdt.get("sdt_gdt") or "").strip()
    # Đuôi "     ." sau SĐT như mẫu cũ: máy in tự cắt phần trắng cuối tờ nên khoảng trống
    # nướng vào ảnh không ra giấy — phải có 1 dấu chấm ở xa để máy in in tới đó, tạo
    # chỗ trống bên phải SĐT (Duy 2026-09-22). Dùng em-space (không bị gộp như space).
    nhan = f"Người nhận: {ten}" + (f" {sdt}" if sdt else "") + TAIL_MARK
    lines = [f"Người gửi: {sender}", nhan, f"{str(gdt.get('so_thung') or '').strip()} (thùng)"]
    note = str(gdt.get("note_gdt") or "").strip()
    if note:
        lines.append(note)
    return lines


def generate_gdt_html(gdt: dict, sender: str | None = None, preview: bool = False) -> str:
    """HTML nhãn. `preview=True` vẽ khung mảnh quanh nhãn để ảnh xem trước (bị crop
    nền trắng) vẫn giữ đúng tỉ lệ tờ giấy."""
    lines = label_lines(gdt, sender)
    ps = "".join(f'<p style="font-size:{fit_font_px(t)}px">{esc(t)}</p>' for t in lines)
    frame = "outline:1px solid #bbb;" if preview else ""
    return f'''<!DOCTYPE html><html lang="vi"><head>
<meta charset="UTF-8" />
<title>Giấy dán thùng</title>
<style>
  @page {{ margin: 0; }}
  html, body {{ margin: 0; padding: 0; background: #fff; }}
  body {{ width: {LABEL_W}px; }}
  .label {{ width: {LABEL_W}px; height: {LABEL_H}px; box-sizing: border-box; padding: 0 {SIDE_PAD}px; {frame}
    display: flex; flex-direction: column; justify-content: space-around; align-items: center;
    writing-mode: vertical-rl; font-family: Arial, Helvetica, sans-serif; font-weight: 700;
    line-height: 1.15; overflow: hidden; color: #000; }}
  .label p {{ margin: 0; white-space: nowrap; }}
</style>
</head><body><div class="label">{ps}</div></body></html>'''


def generate_gdt_print_html(png: bytes, width_px: int = LABEL_W) -> str:
    """HTML GỬI MÁY IN: chỉ 1 ảnh PNG của nhãn (render từ generate_gdt_html) nằm trong
    dòng chảy bình thường như hoá đơn. Lý do (in thử 21/09/2026): gửi thẳng HTML chữ
    xoay dọc + khối cao cố định thì máy in cắt ngang ở ~80mm và ép nội dung vào nửa
    trái giấy — client in không dựng đúng layout đó, nhưng hoá đơn (dòng chảy, ảnh QR)
    thì in dài được. Ảnh nhúng data-URI để máy in không cần mạng."""
    b64 = base64.b64encode(png).decode("ascii")
    return f'''<!DOCTYPE html><html lang="vi"><head>
<meta charset="UTF-8" />
<title>Giấy dán thùng</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #fff; }}
  body {{ width: {width_px}px; }}
  img {{ display: block; max-width: {width_px}px; margin: 0 auto; }}
</style>
</head><body><img src="data:image/png;base64,{b64}" alt="Giấy dán thùng" /></body></html>'''
