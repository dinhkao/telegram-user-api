"""SOI GHI CHÚ báo cáo thợ — dòng nào ghi TAY khác từ khoá phụ cấp đã cài sẵn.

Phụ cấp tự động (production_store.allowance_auto) CHỈ trả khi ghi chú TRÙNG KHÍT 1
câu chuẩn (PHRASES, từ 2026-09-26). Ghi chú lệch chuẩn ("vít 25k", "vít tới 8h", "gỡ
bánh") thì auto im lặng không ghi gì — văn phòng phải tự quyết. Module này SO KHÍT ghi
chú với câu chuẩn rồi gom nhóm MỌI dòng không trùng khít cho dashboard sản xuất cảnh
báo, và `needs_review` cho dấu ⚠ ở ô bảng lương SP theo ngày (wage_pivot). Nối: allowance_auto (RULES), report_rows
(production_report_rows), allowances (production_allowances), vn.vn_normalize.
"""
from __future__ import annotations

import re

from vn import vn_normalize
from production_store.allowance_auto import PHRASES, RULES, _NGHI, _has_kw, fold_note, parse_note_amount

# Phân loại 1 ghi chú (so với bảng RULES):
KIND_MATCH = "khop"       # khớp từ khoá CỦA CHÍNH thợ đó (hoặc "nghỉ") → auto chạy đúng
KIND_OTHER = "khac_tho"   # là từ khoá có phụ cấp, nhưng KHÔNG phải của thợ này
KIND_QTY = "so_luong"     # chỉ ghi số lượng/giờ ("đã -1 mâm", "về 10h") — không phải việc
KIND_UNKNOWN = "la"       # chữ lạ, không nằm trong bảng → cần xem lại phụ cấp
KIND_AMOUNT = "so_tien"   # ghi chú CÓ SỐ TIỀN viết tay ("vít 25k") → auto KHÔNG trả, cần nhập tay
KIND_PARTIAL = "mot_phan"  # chứa từ khoá của CHÍNH thợ nhưng CÒN CHỮ THỪA → auto KHÔNG trả

# CẢNH BÁO MỌI THỨ KHÔNG TRÙNG KHÍT (Duy chốt 2026-09-12: "đưa vào hết") — chỉ `khop`
# là sạch. Viết theo kiểu "trừ khop" để thêm loại mới về sau không bị quên khỏi danh
# sách. Thứ tự = mức cần xử lý: so_tien / mot_phan là thợ CÓ làm việc có phụ cấp mà auto
# không trả (lệch câu chuẩn); la / khac_tho là việc lạ; so_luong chỉ là chỉnh số.
FLAG_KINDS = (KIND_AMOUNT, KIND_PARTIAL, KIND_UNKNOWN, KIND_OTHER, KIND_QTY)

ALL_KEYWORDS: frozenset[str] = frozenset(
    [_NGHI] + [k for _, kws, _ in RULES for k in kws]
)

# CÂU ghi chú chuẩn + cách fold dùng CHUNG với allowance_auto (auto chỉ trả khi trùng
# khít — 2026-09-26), để "cảnh báo" và "được trả" không bao giờ lệch nhau.
_PHRASES = PHRASES
_fold = fold_note


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
    # Có số tiền viết tay → auto không trả, văn phòng nhập đúng số người ta đã viết.
    if has_money(nf):
        return KIND_AMOUNT
    # Chứa từ khoá của CHÍNH mình nhưng còn chữ thừa ("vít tới 8h", "chiên dauu") →
    # auto KHÔNG trả (phải trùng khít) — văn phòng tự quyết số tiền.
    if any(_has_kw(nf, k) for k in keywords_for(worker_name)):
        return KIND_PARTIAL
    if any(_has_kw(nf, k) for k in ALL_KEYWORDS):
        return KIND_OTHER
    return KIND_QTY if _is_qty_only(nf) else KIND_UNKNOWN


# Loại ghi chú gắn dấu ⚠ ở ô bảng lương SP theo ngày: có dính tới việc/tiền mà auto
# KHÔNG trả. Bỏ `so_luong` ("Đã -1 mâm", "về 10h") — chỉ chỉnh số, không phải việc có
# phụ cấp, gắn dấu thì cả bảng lốm đốm mất tác dụng gây chú ý.
PIVOT_FLAG_KINDS = (KIND_AMOUNT, KIND_PARTIAL, KIND_UNKNOWN, KIND_OTHER)


def needs_review(worker_name: str, note: str) -> str:
    """THUẦN. Loại ghi chú (KIND_*) nếu ô này cần văn phòng xem lại phụ cấp, "" nếu không."""
    k = note_kind(worker_name, note)
    return k if k in PIVOT_FLAG_KINDS else ""


def _fmt_row(r, kind: str) -> dict:
    return {
        "thread_id": r["thread_id"], "ymd": r["ymd"], "date": r["report_date"],
        # worker_raw + note_fold = KHOÁ đánh dấu đã-xử-lý (production_note_resolved);
        # `worker` là tên hiển thị (có thể đã đổi tên) — đừng dùng nó làm khoá.
        "worker": r["worker"], "worker_raw": r["worker_raw"], "note_fold": _fold(r["note"]),
        "note": r["note"], "kind": kind,
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

    Dòng đã tick xử lý (production_note_resolved) VẪN NẰM TRONG kết quả, mang cờ
    `done`; nhóm có `done` = số dòng đã tick. Nhóm xong hết chìm xuống cuối mục của
    nó chứ không biến mất.
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
        "       COALESCE(w.name, t.worker_name) AS worker, t.worker_name AS worker_raw, "
        "       TRIM(t.note) AS note, "
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

    from production_store.note_resolved import resolved_keys
    done = resolved_keys(conn)
    n_done = 0
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
        # Dòng đã tick VẪN HIỆN (Duy chốt 2026-09-12) — chỉ gắn cờ để client tô mờ +
        # tick sẵn. Giấu đi thì không còn cách xem lại mình đã xử lý cái gì, mà bỏ tick
        # nhầm cũng không sửa được.
        is_done = (int(r["thread_id"]), str(r["worker_raw"] or ""), nf) in done
        if is_done:
            n_done += 1
        key = (r["worker"] or "", nf, kind)
        dedup = (r["thread_id"], r["worker"], nf)
        if dedup in seen:
            continue
        seen.add(dedup)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "worker": r["worker"], "note": r["note"], "kind": kind,
                "count": 0, "done": 0, "paid": 0, "last_ymd": r["ymd"], "rows": [],
            }
        g["count"] += 1
        if is_done:
            g["done"] += 1
        if float(r["allow"] or 0) > 0:
            g["paid"] += 1
        if len(g["rows"]) < sample:
            row = _fmt_row(r, kind)
            row["done"] = is_done
            g["rows"].append(row)
    _order = {KIND_AMOUNT: 0, KIND_PARTIAL: 1, KIND_UNKNOWN: 2, KIND_OTHER: 3, KIND_QTY: 4}
    out = sorted(
        groups.values(),
        key=lambda g: (_order.get(g["kind"], 9), g["done"] >= g["count"],
                       -g["count"], g["worker"]),
    )
    return {
        "groups": out,
        "counts": counts,
        "flagged": sum(g["count"] for g in out),
        "resolved": n_done,               # đã tick xử lý trong khoảng này
        "truncated": len(rows) >= max_scan,
    }


def group_row_keys(conn, worker: str, note: str,
                   dfrom: str | None = None, dto: str | None = None) -> list[tuple[int, str, str]]:
    """Khoá của MỌI dòng thuộc nhóm (thợ, ghi chú) trong khoảng — để tick cả nhóm.

    Nhóm trên UI chỉ mang tối đa `sample` dòng, nên tick-cả-nhóm phải hỏi lại server
    chứ không gửi danh sách từ client. Khớp thợ bằng CÙNG biểu thức với review_notes
    (COALESCE tên hiện hành) và so ghi chú theo dạng đã fold — hai bên luôn ra cùng tập.
    """
    where = "WHERE TRIM(COALESCE(t.note,'')) != '' AND COALESCE(w.name, t.worker_name) = ?"
    args: list = [worker]
    if dfrom:
        where += " AND t.report_ymd >= ?"
        args.append(dfrom)
    if dto:
        where += " AND t.report_ymd <= ?"
        args.append(dto)
    target = _fold(note)
    rows = conn.execute(
        "SELECT t.thread_id AS thread_id, t.worker_name AS worker_raw, TRIM(t.note) AS note "
        "FROM production_report_rows t "
        "LEFT JOIN production_workers w ON w.id = t.worker_id "
        f"{where}", args,
    ).fetchall()
    return [(int(r["thread_id"]), str(r["worker_raw"] or ""), target)
            for r in rows if _fold(r["note"]) == target]
