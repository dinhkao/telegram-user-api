"""Bảng `entity_image_scores` (app.db) — CHẤM ĐIỂM 0–10 cho TỪNG ẢNH của
entity_media_store (scope ẢNH-THUỘC-BÁO-CÁO, vd 'area_report' | 'quality_report').

⚠ MỖI NGƯỜI MỘT ĐIỂM RIÊNG: khoá chính là (scope, image_id, **scored_by**) — một
ảnh có thể được nhiều người chấm, mỗi người giữ điểm của mình, chấm lại chỉ ghi đè
điểm CỦA MÌNH, bỏ điểm cũng chỉ bỏ của mình. `scored_by` = USERNAME (web_auth
middleware gắn request['web_user'] là username, ổn định hơn tên hiển thị).

Trước đây khoá là (scope, image_id) → 1 ảnh 1 điểm, ai chấm sau ĐÈ người trước.
`_migrate_per_user` tự nâng cấp bảng cũ (SQLite không ALTER được PRIMARY KEY nên
phải dựng bảng mới + copy + đổi tên); dữ liệu cũ thành điểm của chính người đã chấm.

Điểm gộp: `scores_for` trả TRUNG BÌNH các người chấm + điểm của người đang xem;
`avg_by_entity` lấy trung bình CỦA TỪNG ẢNH rồi mới trung bình theo báo cáo — để
một ảnh nhiều người chấm không bị tính nặng hơn ảnh chỉ một người chấm.
Connection qua utils.db. Dùng bởi: server_app/image_score_routes, photo_report_view.
"""
from __future__ import annotations

import time

from utils.db import get_connection, transaction

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS entity_image_scores (
    scope      TEXT NOT NULL,
    image_id   INTEGER NOT NULL,
    score      INTEGER NOT NULL,
    scored_by  TEXT NOT NULL DEFAULT '?',
    scored_at  INTEGER NOT NULL,
    PRIMARY KEY (scope, image_id, scored_by)
)
"""
_IDX = ("CREATE INDEX IF NOT EXISTS idx_image_scores_lookup "
        "ON entity_image_scores(scope, image_id)")

_ensured: set[str] = set()

SCORE_MIN, SCORE_MAX = 0, 10


def _migrate_per_user(conn) -> bool:
    """Nâng khoá chính (scope,image_id) → (scope,image_id,scored_by). Idempotent.
    Trả True nếu vừa nâng cấp. Bảng chưa tồn tại thì không làm gì (_CREATE_SQL
    sẽ tạo thẳng bảng đúng chuẩn mới)."""
    cols = conn.execute("PRAGMA table_info(entity_image_scores)").fetchall()
    if not cols:
        return False
    pk = {r["name"]: int(r["pk"] or 0) for r in cols}
    if pk.get("scored_by"):
        return False                      # đã ở chuẩn mới
    with transaction(conn):
        conn.execute("DROP TABLE IF EXISTS entity_image_scores_new")
        conn.execute(_CREATE_SQL.replace("entity_image_scores", "entity_image_scores_new"))
        # bảng cũ 1 ảnh 1 dòng nên không thể đụng khoá mới; giữ nguyên ai chấm/lúc nào
        conn.execute(
            "INSERT INTO entity_image_scores_new (scope, image_id, score, scored_by, scored_at) "
            "SELECT scope, image_id, score, COALESCE(NULLIF(scored_by, ''), '?'), scored_at "
            "FROM entity_image_scores"
        )
        conn.execute("DROP TABLE entity_image_scores")
        conn.execute("ALTER TABLE entity_image_scores_new RENAME TO entity_image_scores")
    return True


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        _migrate_per_user(conn)
        conn.execute(_IDX)
        # avg_by_entity JOIN sang entity_images → bảng đó cũng phải tồn tại kể cả
        # khi chưa ai upload ảnh trong process này (nếu không: "no such table").
        from .images import _CREATE_SQL as _IMG_SQL
        conn.execute(_IMG_SQL)
        _ensured.add(key)
    return conn


def parse_score(value) -> int:
    """Ép điểm về int 0–10. Raise ValueError nếu không phải số / ngoài thang."""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        raise ValueError("Điểm phải là số 0–10")
    if n < SCORE_MIN or n > SCORE_MAX:
        raise ValueError("Điểm phải trong thang 0–10")
    return n


def set_score(scope: str, image_id: int, score, by: str = "?", *, db_path: str | None = None) -> dict:
    """Chấm điểm ảnh CHO NGƯỜI `by`. Chấm lại = ghi đè điểm của chính người đó,
    KHÔNG đụng điểm người khác."""
    n = parse_score(score)
    who = (by or "?").strip() or "?"
    now = int(time.time())
    conn = _conn(db_path)
    try:
        conn.execute(
            "INSERT INTO entity_image_scores (scope, image_id, score, scored_by, scored_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(scope, image_id, scored_by) DO UPDATE SET "
            "score = excluded.score, scored_at = excluded.scored_at",
            (scope, int(image_id), n, who, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"image_id": int(image_id), "score": n, "scored_by": who, "scored_at": now}


def clear_score(scope: str, image_id: int, by: str | None = None, *, db_path: str | None = None) -> bool:
    """Bỏ điểm. `by` = bỏ điểm CỦA NGƯỜI ĐÓ (dùng ở API — không ai xoá điểm người
    khác được). by=None = xoá điểm của MỌI người (dọn khi xoá hẳn ảnh)."""
    conn = _conn(db_path)
    try:
        if by is None:
            cur = conn.execute(
                "DELETE FROM entity_image_scores WHERE scope = ? AND image_id = ?",
                (scope, int(image_id)))
        else:
            cur = conn.execute(
                "DELETE FROM entity_image_scores WHERE scope = ? AND image_id = ? AND scored_by = ?",
                (scope, int(image_id), (by or "?").strip() or "?"))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def scores_for(scope: str, image_ids: list[int], viewer: str | None = None, *,
               db_path: str | None = None) -> dict[int, dict]:
    """{image_id: {score, score_count, my_score, my_scored_at, raters:[…]}} cho các
    ảnh CÓ ít nhất 1 điểm.
      score       = trung bình các người chấm (1 chữ số thập phân)
      score_count = số NGƯỜI đã chấm ảnh đó
      my_score    = điểm của `viewer` (None nếu người đó chưa chấm / không truyền)
      raters      = [{by, score, at}] sắp theo lúc chấm, để hiện "ai cho mấy điểm"
    """
    ids = [int(i) for i in (image_ids or [])]
    if not ids:
        return {}
    me = (viewer or "").strip()
    conn = _conn(db_path)
    try:
        out: dict[int, dict] = {}
        for i in range(0, len(ids), 400):   # tránh vượt trần biến SQLite
            chunk = ids[i:i + 400]
            q = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT image_id, score, scored_by, scored_at FROM entity_image_scores "
                f"WHERE scope = ? AND image_id IN ({q}) ORDER BY scored_at, scored_by",
                (scope, *chunk),
            ).fetchall()
            for r in rows:
                iid = int(r["image_id"])
                who = r["scored_by"] or ""
                e = out.setdefault(iid, {"score": None, "score_count": 0, "my_score": None,
                                         "my_scored_at": None, "raters": []})
                e["raters"].append({"by": who, "score": int(r["score"]),
                                    "at": int(r["scored_at"] or 0)})
                if me and who == me:
                    e["my_score"] = int(r["score"])
                    e["my_scored_at"] = int(r["scored_at"] or 0)
        for e in out.values():
            n = len(e["raters"])
            e["score_count"] = n
            e["score"] = round(sum(x["score"] for x in e["raters"]) / n, 1) if n else None
        return out
    finally:
        conn.close()


def avg_by_entity(scope: str, entity_ids: list[int], *, db_path: str | None = None) -> dict[int, dict]:
    """{entity_id: {avg, count}} — `avg` = trung bình ĐIỂM TỪNG ẢNH (ảnh nào nhiều
    người chấm thì lấy trung bình của ảnh đó trước), `count` = SỐ ẢNH đã có điểm.
    Làm 2 tầng để 1 ảnh 5 người chấm không nặng gấp 5 ảnh 1 người chấm.
    Thực thể chưa ảnh nào được chấm thì không có khoá."""
    ids = [int(i) for i in (entity_ids or [])]
    if not ids:
        return {}
    conn = _conn(db_path)
    try:
        out: dict[int, dict] = {}
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            q = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT eid, AVG(img_avg) AS avg_score, COUNT(*) AS n FROM ("
                f"  SELECT i.entity_id AS eid, s.image_id AS iid, AVG(s.score) AS img_avg"
                f"  FROM entity_image_scores s JOIN entity_images i ON i.id = s.image_id"
                f"  WHERE s.scope = ? AND i.scope = ? AND i.entity_id IN ({q})"
                f"  GROUP BY i.entity_id, s.image_id"
                f") GROUP BY eid",
                (scope, scope, *chunk),
            ).fetchall()
            for r in rows:
                out[int(r["eid"])] = {"avg": round(float(r["avg_score"]), 1), "count": int(r["n"])}
        return out
    finally:
        conn.close()
