"""Bảng `entity_image_scores` (app.db) — CHẤM ĐIỂM 0–10 cho TỪNG ẢNH của
entity_media_store (khoá theo (scope, image_id) — scope là scope ẢNH, vd
'area_report' | 'quality_report').

1 ảnh có TỐI ĐA 1 điểm (chấm lại = ghi đè, lưu ai chấm + lúc nào). Điểm là số
nguyên 0–10; xoá điểm = clear_score. avg_by_entity gộp điểm trung bình theo THỰC
THỂ chứa ảnh (báo cáo ngày) để dashboard hiện điểm mà không phải tải từng ảnh.
Connection qua utils.db. Dùng bởi: server_app/entity_media_routes, area_routes,
quality_routes.
"""
from __future__ import annotations

import time

from utils.db import get_connection

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS entity_image_scores (
    scope      TEXT NOT NULL,
    image_id   INTEGER NOT NULL,
    score      INTEGER NOT NULL,
    scored_by  TEXT NOT NULL DEFAULT '?',
    scored_at  INTEGER NOT NULL,
    PRIMARY KEY (scope, image_id)
)
"""

_ensured: set[str] = set()

SCORE_MIN, SCORE_MAX = 0, 10


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
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
    """Chấm/ghi đè điểm 1 ảnh. Trả dòng điểm mới."""
    n = parse_score(score)
    now = int(time.time())
    conn = _conn(db_path)
    try:
        conn.execute(
            "INSERT INTO entity_image_scores (scope, image_id, score, scored_by, scored_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(scope, image_id) DO UPDATE SET "
            "score = excluded.score, scored_by = excluded.scored_by, scored_at = excluded.scored_at",
            (scope, int(image_id), n, by or "?", now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"image_id": int(image_id), "score": n, "scored_by": by or "?", "scored_at": now}


def clear_score(scope: str, image_id: int, *, db_path: str | None = None) -> bool:
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM entity_image_scores WHERE scope = ? AND image_id = ?", (scope, int(image_id))
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def scores_for(scope: str, image_ids: list[int], *, db_path: str | None = None) -> dict[int, dict]:
    """{image_id: {score, scored_by, scored_at}} cho các ảnh có điểm."""
    ids = [int(i) for i in (image_ids or [])]
    if not ids:
        return {}
    conn = _conn(db_path)
    try:
        out: dict[int, dict] = {}
        for i in range(0, len(ids), 400):   # tránh vượt trần biến SQLite
            chunk = ids[i:i + 400]
            q = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT image_id, score, scored_by, scored_at FROM entity_image_scores "
                f"WHERE scope = ? AND image_id IN ({q})",
                (scope, *chunk),
            ).fetchall()
            for r in rows:
                out[int(r["image_id"])] = {"score": int(r["score"]),
                                           "scored_by": r["scored_by"] or "",
                                           "scored_at": int(r["scored_at"] or 0)}
        return out
    finally:
        conn.close()


def avg_by_entity(scope: str, entity_ids: list[int], *, db_path: str | None = None) -> dict[int, dict]:
    """{entity_id: {avg, count}} — điểm TRUNG BÌNH các ảnh ĐÃ CHẤM của từng thực
    thể (join entity_images). Thực thể chưa ảnh nào được chấm thì không có khoá."""
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
                f"SELECT i.entity_id AS eid, AVG(s.score) AS avg_score, COUNT(*) AS n "
                f"FROM entity_image_scores s JOIN entity_images i ON i.id = s.image_id "
                f"WHERE s.scope = ? AND i.scope = ? AND i.entity_id IN ({q}) "
                f"GROUP BY i.entity_id",
                (scope, scope, *chunk),
            ).fetchall()
            for r in rows:
                out[int(r["eid"])] = {"avg": round(float(r["avg_score"]), 1), "count": int(r["n"])}
        return out
    finally:
        conn.close()
