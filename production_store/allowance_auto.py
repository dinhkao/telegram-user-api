"""PHỤ CẤP TỰ ĐỘNG theo GHI CHÚ báo cáo thợ — chạy mỗi lần lưu báo cáo (set_bang).

Rule (sửa bảng RULES bên dưới): thợ X có ghi chú chứa từ khoá Y → phụ cấp = TIỀN SP
(không tính phụ cấp) của người cao nhất/nhì bảng phiếu đó. Ai có ghi chú "nghỉ" →
xoá phụ cấp. Ghi với updated_by='auto' — văn phòng sửa tay (updated_by khác) thì
auto KHÔNG đè nữa (trừ rule "nghỉ" vẫn ép xoá). Nối: production_allowances (qua
allowances.set_allowance), production_slips + production_workers (tính tiền SP),
production_store.wages, vn.vn_normalize.
"""
from __future__ import annotations

import re

from vn import vn_normalize

# ── Bảng RULE: ({tên thợ đã bỏ dấu}, (từ khoá ghi chú đã bỏ dấu, ...), hạng) ──
# hạng: 0 = bằng tiền SP người CAO NHẤT bảng, 1 = cao NHÌ, 2 = cao BA.
RULES: list[tuple[set[str], tuple[str, ...], int]] = [
    ({"kim"}, ("vit",), 0),                          # Kim + "vít…" → cao nhất
    ({"duy"}, ("vit", "rac me"), 1),                 # Duy + "vít"/"rắc mè" → cao nhì
    ({"kim dung", "bao", "xuyen"}, ("quay keo",), 0),  # quậy kẹo → cao nhất
    ({"thuy dang"}, ("quay keo",), 1),               # Thủy Đặng + quậy kẹo → cao nhì
]
_NGHI = "nghi"   # ghi chú "nghỉ" → không phụ cấp (ưu tiên trên mọi rule)
# Thợ KHÔNG dùng làm MỐC xếp hạng phụ cấp (sản lượng cao bất thường — không nên là
# mốc cho người khác). Tên đã bỏ dấu.
RANK_EXCLUDE = {"tran"}

_AUTO_BY = "auto"


def _has_kw(note_fold: str, kw: str) -> bool:
    """Từ khoá khớp theo RANH GIỚI TỪ ('nghi' không ăn 'nghiem')."""
    return re.search(rf"\b{re.escape(kw)}\b", note_fold) is not None


def compute_auto_allowances(workers: list[dict]) -> dict[str, float]:
    """THUẦN. workers = [{name, piece, note, hour}] (piece = tiền đã tính, không phụ
    cấp; hour = True nếu người này TÍNH LƯƠNG THEO GIỜ phiếu này).

    Trả {name: amount} CHỈ cho thợ có rule khớp; amount 0 = xoá phụ cấp (rule nghỉ).
    MỐC xếp hạng = thợ làm CÂY: bỏ người tính theo GIỜ (tiền giờ không làm mốc) và bỏ
    thợ trong RANK_EXCLUDE (Trân). Người tính theo GIỜ cũng KHÔNG nhận phụ cấp."""
    ranked = sorted(
        (w for w in workers
         if not w.get("hour")
         and vn_normalize(str(w.get("name") or "")).strip() not in RANK_EXCLUDE),
        key=lambda w: (-float(w.get("piece") or 0), vn_normalize(str(w.get("name") or ""))),
    )
    out: dict[str, float] = {}
    for w in workers:
        name = str(w.get("name") or "").strip()
        if not name:
            continue
        note = vn_normalize(str(w.get("note") or ""))
        if _has_kw(note, _NGHI):
            out[name] = 0.0
            continue
        if w.get("hour"):        # tính lương theo giờ → không có phụ cấp
            continue
        nfold = vn_normalize(name).strip()
        for names, kws, rank in RULES:
            if nfold in names and any(_has_kw(note, k) for k in kws):
                if rank < len(ranked):
                    out[name] = float(ranked[rank].get("piece") or 0)
                break
    return out


def _pieces_from_bang(conn, thread_id: int, bang: dict) -> list[dict]:
    """[{name, piece, note, hour}] từ blob bang vừa lưu — cùng công thức khối tiền công
    UI: dòng có GIỜ (phiếu sản xuất) = giờ × tiền-1-giờ của thợ (hour=True), còn lại =
    cây × đơn giá chốt theo phiếu (fallback bảng lương)."""
    rows = bang.get("rows") or []
    if not rows:
        return []
    slip = conn.execute(
        "SELECT sp_name, luong_1sp, kind FROM production_slips WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    code = str(bang.get("product_code") or (slip["sp_name"] if slip else "") or "").strip().upper()
    if slip is not None and slip["luong_1sp"] is not None:
        wage = float(slip["luong_1sp"])
    else:
        from production_store.wages import wage_per_cay
        wage = wage_per_cay(code)
    hourly_ok = ((slip["kind"] if slip else None) or "san_xuat") != "dong_goi"
    try:
        hourly = {vn_normalize(r[0]): float(r[1] or 0) for r in conn.execute(
            "SELECT name, hourly_rate FROM production_workers").fetchall()}
    except Exception:
        hourly = {}
    out = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        gio = float(r.get("so_gio") or 0) if hourly_ok else 0.0
        cay = float(r.get("tong_calc") or 0)
        rate = hourly.get(vn_normalize(name), 0.0)
        piece = round(gio * rate) if gio > 0 else round(cay * wage)
        out.append({"name": name, "piece": piece, "note": str(r.get("note") or ""), "hour": gio > 0})
    return out


def apply_auto_allowances(conn, thread_id: int, bang: dict) -> None:
    """Áp rule sau khi lưu báo cáo. Chỉ đụng dòng do auto ghi (updated_by='auto')
    hoặc chưa có; văn phòng đã sửa tay thì giữ nguyên — trừ "nghỉ" vẫn ép xoá.
    Thợ hết khớp rule → gỡ phụ cấp auto cũ (số tay giữ nguyên)."""
    from production_store.allowances import ensure_schema, set_allowance

    workers = _pieces_from_bang(conn, thread_id, bang)
    if not workers:
        return
    targets = compute_auto_allowances(workers)
    ensure_schema(conn)
    existing = {r[0]: (float(r[1] or 0), r[2] or "") for r in conn.execute(
        "SELECT worker_name, amount, updated_by FROM production_allowances WHERE thread_id = ?",
        (thread_id,),
    ).fetchall()}
    for w in workers:
        name = w["name"]
        cur = existing.get(name)
        tgt = targets.get(name)
        if tgt is None:
            # không khớp rule nào — chỉ dọn dòng auto cũ, số nhập tay giữ nguyên
            if cur and cur[1] == _AUTO_BY:
                set_allowance(conn, thread_id, name, 0, by=_AUTO_BY)
            continue
        if cur and cur[1] not in ("", _AUTO_BY) and tgt > 0:
            continue                     # văn phòng đã sửa tay → tôn trọng
        if cur is None and tgt <= 0:
            continue                     # chưa có gì để xoá
        if cur is not None and abs(cur[0] - tgt) < 0.5:
            continue                     # không đổi — khỏi ghi lại
        set_allowance(conn, thread_id, name, tgt, by=_AUTO_BY)
