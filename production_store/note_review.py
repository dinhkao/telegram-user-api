"""SOI GHI CHÚ báo cáo thợ — dòng nào ghi TAY khác từ khoá phụ cấp đã cài sẵn.

Phụ cấp tự động (production_store.allowance_auto) khớp ghi chú theo TỪ KHOÁ cố định
trong bảng RULES — khớp LỎNG (chỉ cần CHỨA từ khoá). Nên "vít 25k" vẫn khớp "vít" rồi
auto ghi tiền theo hạng, bỏ qua số 25k người ta viết; còn "gỡ bánh" thì không được
tính đồng nào — cả hai đều im lặng. Module này SO KHÍT ghi chú với câu chuẩn rồi gom
nhóm MỌI dòng không trùng khít cho dashboard sản xuất cảnh báo. Nối: allowance_auto (RULES), report_rows
(production_report_rows), allowances (production_allowances), vn.vn_normalize.
"""
from __future__ import annotations

import re

from vn import vn_normalize
from production_store.allowance_auto import RULES, _NGHI, _has_kw, parse_note_amount

# Phân loại 1 ghi chú (so với bảng RULES):
KIND_MATCH = "khop"       # khớp từ khoá CỦA CHÍNH thợ đó (hoặc "nghỉ") → auto chạy đúng
KIND_OTHER = "khac_tho"   # là từ khoá có phụ cấp, nhưng KHÔNG phải của thợ này
KIND_QTY = "so_luong"     # chỉ ghi số lượng/giờ ("đã -1 mâm", "về 10h") — không phải việc
KIND_UNKNOWN = "la"       # chữ lạ, không nằm trong bảng → cần xem lại phụ cấp
KIND_AMOUNT = "so_tien"   # ghi chú CÓ SỐ TIỀN viết tay ("vít 25k") → auto ĐÈ số khác
KIND_PARTIAL = "mot_phan"  # chứa từ khoá của CHÍNH thợ nhưng CÒN CHỮ THỪA → auto VẪN tính

# CẢNH BÁO MỌI THỨ KHÔNG TRÙNG KHÍT (Duy chốt 2026-09-12: "đưa vào hết") — chỉ `khop`
# là sạch. Viết theo kiểu "trừ khop" để thêm loại mới về sau không bị quên khỏi danh
# sách. Thứ tự = mức nguy hiểm: so_tien / mot_phan là ca auto VẪN GHI TIỀN (chữ thừa
# bị bỏ qua âm thầm); la / khac_tho là "không được tính"; so_luong chỉ là chỉnh số.
FLAG_KINDS = (KIND_AMOUNT, KIND_PARTIAL, KIND_UNKNOWN, KIND_OTHER, KIND_QTY)

ALL_KEYWORDS: frozenset[str] = frozenset(
    [_NGHI] + [k for _, kws, _ in RULES for k in kws]
)

# ── CÂU ghi chú ĐÚNG CHUẨN (Duy chốt 2026-09-12: "bất cứ text nào ko fit 100% đều
# filter hết") ────────────────────────────────────────────────────────────────────
# `allowance_auto.RULES` khớp LỎNG theo từ khoá là CỐ Ý (mảnh "chien" phải bắt được
# cả "Chiên đậu"), nên không thể so khít với chính RULES. Bảng dưới là DẠNG ĐẦY ĐỦ
# mà thợ được phép ghi cho mỗi từ khoá. Ghi chú phải TRÙNG KHÍT một câu ở đây (sau
# khi bỏ dấu + gộp khoảng trắng) mới coi là chuẩn; thừa một chữ cũng vào diện xem lại.
# Số liệu 01/06→12/09/2026: 2.323 dòng được auto tính chỉ dùng 9 câu dưới đây, 12
# dòng còn lại là ghi tay ("vít tới 8h", "chiên dauu", "vít 30p"…) — đúng thứ cần soi.
# THÊM CÂU MỚI Ở ĐÂY khi xưởng đổi cách ghi; đừng nới lỏng lại thành so-chứa.
_PHRASES: dict[str, tuple[str, ...]] = {
    "vit": ("vit", "vit keo"),
    "quay keo": ("quay keo",),
    "chien": ("chien", "chien dau"),
    "rac me": ("rac me",),
    "vo keo": ("vo keo",),
    "rac com dua": ("rac com dua",),
    "rac dua": ("rac dua",),
    "gan dua": ("gan dua",),
    _NGHI: (_NGHI,),
}

_WS_RE = re.compile(r"\s+")


def _fold(note: str) -> str:
    """Bỏ dấu + gộp khoảng trắng — dạng dùng để so khít."""
    return _WS_RE.sub(" ", vn_normalize(str(note or "")).strip())


def keywords_for(worker_name: str) -> frozenset[str]:
    """Từ khoá CÓ PHỤ CẤP của riêng thợ này (đã gộp mọi rule khớp tên)."""
    nf = vn_normalize(str(worker_name or "")).strip()
    out: set[str] = {_NGHI}
    for names, kws, _ in RULES:
        if nf in names:
            out.update(kws)
    return frozenset(out)


def phrases_for(worker_name: str) -> frozenset[str]:
    """CÂU đầy đủ mà thợ này được phép ghi (từ khoá của họ → dạng ghi hợp lệ)."""
    out: set[str] = set()
    for kw in keywords_for(worker_name):
        out.update(_PHRASES.get(kw, (kw,)))
    return frozenset(out)


# ── Nhận diện ghi chú CHỈ CHỈNH SỐ / GIỜ (không phải việc) ─────────────────────
# "Đã -1 mâm", "đã +1 gạch", "+2c", "về 10h", "vô 7h40"… Bóc hết các mảnh này ra;
# còn lại chữ nào thì đó mới là nội dung việc. (Dạng "vít 15k" KHÔNG rơi vào đây —
# `has_money` bắt trước ở note_kind, xem khối dưới.)
_QTY_PIECES = [
    r"[+-]?\s*\d+(?:[.,]\d+)?\s*(?:mam|man|gach|cay|kg|k|c|p|ph|phut|tieng|gio)\b",
    r"\b\d{1,2}\s*[hg:]\s*\d{0,2}\b",          # 10h, 4h30, 15:40
    r"\b(?:da|ve|vo|toi|den|luc|tu|con|khoang)\b",
    r"\d",                                      # số lẻ còn sót
]
_QTY_RE = re.compile("|".join(_QTY_PIECES))
_WORD_RE = re.compile(r"[a-z]+")

# ── SỐ TIỀN viết tay trong ghi chú ────────────────────────────────────────────
# Dùng CHUNG bộ nhận diện với allowance_auto (nơi quyết định tiền) — 2 bản regex riêng
# là kiểu gì cũng lệch: cảnh báo nói "có tiền" mà auto không lấy, hoặc ngược lại.
def has_money(note_fold: str) -> bool:
    """THUẦN. Ghi chú (đã bỏ dấu) có kèm số tiền viết tay không."""
    return parse_note_amount(note_fold) is not None


def _is_qty_only(note_fold: str) -> bool:
    """Ghi chú chỉ gồm số lượng/giờ (bóc hết mảnh số/giờ ra là không còn chữ nào)."""
    return not _WORD_RE.search(_QTY_RE.sub(" ", note_fold))


def note_kind(worker_name: str, note: str) -> str:
    """THUẦN. Ghi chú này thuộc loại nào so với bảng RULES của thợ đó.
    Trả "" khi ghi chú trống (không có gì để xét)."""
    nf = _fold(note)
    if not nf:
        return ""
    # TRÙNG KHÍT câu chuẩn của chính thợ đó = auto chạy đúng ý. Mọi thứ khác đều xét tiếp.
    if nf in phrases_for(worker_name):
        return KIND_MATCH
    # Có số tiền viết tay → nặng nhất: auto vẫn ghi số của nó, đè số người ta đã viết.
    if has_money(nf):
        return KIND_AMOUNT
    # Chứa từ khoá của CHÍNH mình nhưng còn chữ thừa ("vít tới 8h", "chiên dauu") →
    # auto VẪN tính tiền và bỏ qua phần thừa, không báo gì.
    if any(_has_kw(nf, k) for k in keywords_for(worker_name)):
        return KIND_PARTIAL
    if any(_has_kw(nf, k) for k in ALL_KEYWORDS):
        return KIND_OTHER
    return KIND_QTY if _is_qty_only(nf) else KIND_UNKNOWN


def _fmt_row(r, kind: str) -> dict:
    return {
        "thread_id": r["thread_id"], "ymd": r["ymd"], "date": r["report_date"],
        "worker": r["worker"], "note": r["note"], "kind": kind,
        "product_code": r["code"] or "?",
        "allowance": round(float(r["allow"] or 0)),
        "allow_by": r["allow_by"] or "",
    }


def review_notes(conn, dfrom: str | None = None, dto: str | None = None,
                 sample: int = 8, max_scan: int = 5000) -> dict:
    """Gom các dòng báo cáo có GHI CHÚ LẠ (không khớp bảng RULES) trong khoảng ngày.

    1 nhóm = 1 cặp (THỢ, ghi chú) — đơn vị để quyết định "có cần thêm rule phụ cấp
    cho người này không". Kèm tối đa `sample` dòng gần nhất + phụ cấp đang có của
    (phiếu, thợ) đó để văn phòng bấm vào phiếu xem lại. Chỉ đọc.
    """
    from production_store.allowances import ensure_schema
    from production_store.report_rows import ensure_report_rows_schema

    ensure_report_rows_schema(conn)
    ensure_schema(conn)
    where = "WHERE TRIM(COALESCE(t.note,'')) != ''"
    args: list = []
    if dfrom:
        where += " AND t.report_ymd >= ?"
        args.append(dfrom)
    if dto:
        where += " AND t.report_ymd <= ?"
        args.append(dto)
    rows = conn.execute(
        "SELECT t.thread_id AS thread_id, t.report_ymd AS ymd, t.report_date AS report_date, "
        "       COALESCE(w.name, t.worker_name) AS worker, TRIM(t.note) AS note, "
        "       COALESCE(pr.code, t.product_code) AS code, "
        "       a.amount AS allow, a.updated_by AS allow_by "
        "FROM production_report_rows t "
        "LEFT JOIN production_workers w ON w.id = t.worker_id "
        "LEFT JOIN products pr ON pr.id = t.product_id "
        "LEFT JOIN production_allowances a "
        "       ON a.thread_id = t.thread_id AND a.worker_name = t.worker_name "
        f"{where} ORDER BY t.report_ymd DESC, t.thread_id DESC LIMIT ?",
        (*args, max_scan),
    ).fetchall()

    counts: dict[str, int] = {KIND_MATCH: 0, KIND_OTHER: 0, KIND_QTY: 0,
                              KIND_UNKNOWN: 0, KIND_AMOUNT: 0, KIND_PARTIAL: 0}
    groups: dict[tuple[str, str, str], dict] = {}
    seen: set[tuple] = set()          # (phiếu, thợ, ghi chú) — thợ nhiều dòng 1 phiếu
    for r in rows:
        kind = note_kind(r["worker"], r["note"])
        if not kind:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        if kind not in FLAG_KINDS:
            continue
        nf = _fold(r["note"])
        key = (r["worker"] or "", nf, kind)
        dedup = (r["thread_id"], r["worker"], nf)
        if dedup in seen:
            continue
        seen.add(dedup)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "worker": r["worker"], "note": r["note"], "kind": kind,
                "count": 0, "paid": 0, "last_ymd": r["ymd"], "rows": [],
            }
        g["count"] += 1
        if float(r["allow"] or 0) > 0:
            g["paid"] += 1
        if len(g["rows"]) < sample:
            g["rows"].append(_fmt_row(r, kind))
    _order = {KIND_AMOUNT: 0, KIND_PARTIAL: 1, KIND_UNKNOWN: 2, KIND_OTHER: 3, KIND_QTY: 4}
    out = sorted(
        groups.values(),
        key=lambda g: (_order.get(g["kind"], 9), -g["count"], g["worker"]),
    )
    return {
        "groups": out,
        "counts": counts,
        "flagged": sum(g["count"] for g in out),
        "truncated": len(rows) >= max_scan,
    }
