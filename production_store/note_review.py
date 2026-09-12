"""SOI GHI CHÚ báo cáo thợ — dòng nào ghi TAY khác từ khoá phụ cấp đã cài sẵn.

Phụ cấp tự động (production_store.allowance_auto) khớp ghi chú theo TỪ KHOÁ cố định
trong bảng RULES. Thợ ghi kiểu khác ("gỡ bánh", "đổ kẹo"…) thì auto KHÔNG ghi phụ cấp
mà cũng không báo gì → văn phòng dễ bỏ sót. Module này phân loại từng ghi chú rồi gom
nhóm cho dashboard sản xuất cảnh báo. Nối: allowance_auto (RULES), report_rows
(production_report_rows), allowances (production_allowances), vn.vn_normalize.
"""
from __future__ import annotations

import re

from vn import vn_normalize
from production_store.allowance_auto import RULES, _NGHI, _has_kw

# Phân loại 1 ghi chú (so với bảng RULES):
KIND_MATCH = "khop"       # khớp từ khoá CỦA CHÍNH thợ đó (hoặc "nghỉ") → auto chạy đúng
KIND_OTHER = "khac_tho"   # là từ khoá có phụ cấp, nhưng KHÔNG phải của thợ này
KIND_QTY = "so_luong"     # chỉ ghi số lượng/giờ ("đã -1 mâm", "về 10h") — không phải việc
KIND_UNKNOWN = "la"       # chữ lạ, không nằm trong bảng → cần xem lại phụ cấp

FLAG_KINDS = (KIND_UNKNOWN, KIND_OTHER)   # 2 loại đáng cảnh báo

ALL_KEYWORDS: frozenset[str] = frozenset(
    [_NGHI] + [k for _, kws, _ in RULES for k in kws]
)


def keywords_for(worker_name: str) -> frozenset[str]:
    """Từ khoá CÓ PHỤ CẤP của riêng thợ này (đã gộp mọi rule khớp tên)."""
    nf = vn_normalize(str(worker_name or "")).strip()
    out: set[str] = {_NGHI}
    for names, kws, _ in RULES:
        if nf in names:
            out.update(kws)
    return frozenset(out)


# ── Nhận diện ghi chú CHỈ CHỈNH SỐ / GIỜ (không phải việc) ─────────────────────
# "Đã -1 mâm", "đã +1 gạch", "+2c", "về 10h", "vô 7h40", "vít 15k"… Bóc hết các mảnh
# này ra; còn lại chữ nào thì đó mới là nội dung việc.
_QTY_PIECES = [
    r"[+-]?\s*\d+(?:[.,]\d+)?\s*(?:mam|man|gach|cay|kg|k|c|p|ph|phut|tieng|gio)\b",
    r"\b\d{1,2}\s*[hg:]\s*\d{0,2}\b",          # 10h, 4h30, 15:40
    r"\b(?:da|ve|vo|toi|den|luc|tu|con|khoang)\b",
    r"\d",                                      # số lẻ còn sót
]
_QTY_RE = re.compile("|".join(_QTY_PIECES))
_WORD_RE = re.compile(r"[a-z]+")


def _is_qty_only(note_fold: str) -> bool:
    """Ghi chú chỉ gồm số lượng/giờ (bóc hết mảnh số/giờ ra là không còn chữ nào)."""
    return not _WORD_RE.search(_QTY_RE.sub(" ", note_fold))


def note_kind(worker_name: str, note: str) -> str:
    """THUẦN. Ghi chú này thuộc loại nào so với bảng RULES của thợ đó.
    Trả "" khi ghi chú trống (không có gì để xét)."""
    nf = vn_normalize(str(note or "")).strip()
    if not nf:
        return ""
    mine = keywords_for(worker_name)
    if any(_has_kw(nf, k) for k in mine):
        return KIND_MATCH
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

    counts: dict[str, int] = {KIND_MATCH: 0, KIND_OTHER: 0, KIND_QTY: 0, KIND_UNKNOWN: 0}
    groups: dict[tuple[str, str, str], dict] = {}
    seen: set[tuple] = set()          # (phiếu, thợ, ghi chú) — thợ nhiều dòng 1 phiếu
    for r in rows:
        kind = note_kind(r["worker"], r["note"])
        if not kind:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        if kind not in FLAG_KINDS:
            continue
        nf = vn_normalize(r["note"]).strip()
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
    out = sorted(
        groups.values(),
        key=lambda g: (g["kind"] != KIND_UNKNOWN, -g["count"], g["worker"]),
    )
    return {
        "groups": out,
        "counts": counts,
        "flagged": sum(g["count"] for g in out),
        "truncated": len(rows) >= max_scan,
    }
