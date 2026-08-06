"""Dựng dữ liệu XEM cho báo cáo-ảnh-hằng-ngày (vệ sinh khu vực + chất lượng mâm
kẹo) — DÙNG CHUNG bởi server_app/area_routes.py và quality_routes.py.

Mỗi báo cáo (1 ngày) được gắn: ảnh kèm ĐIỂM 0–10 + số bình luận CỦA TỪNG ẢNH
(scope ảnh = `area_image`/`quality_image`, entity_id = image_id), số bình luận của
CẢ NGÀY (scope báo cáo, entity_id = report_id), và điểm TRUNG BÌNH của ngày đó.
Nối: entity_media_store (images/comments/scores).
"""
from __future__ import annotations

from entity_media_store import avg_by_entity, comment_counts, image_counts, list_images, scores_for


def enrich_reports(report_scope: str, image_scope: str, reports: list[dict],
                   viewer: str | None = None) -> None:
    """Gắn images[] (id/điểm/comment_count/người chụp/giờ chụp) + photo_count +
    comment_count + score_avg/score_count vào TỪNG báo cáo (sửa tại chỗ).
    `viewer` = username người đang xem → mỗi ảnh kèm `my_score` (điểm CỦA HỌ) vì
    điểm chấm là RIÊNG TỪNG NGƯỜI."""
    rids = [int(r["id"]) for r in reports]
    if not rids:
        return
    counts = image_counts(report_scope, rids)
    day_comments = comment_counts(report_scope, rids)
    day_scores = avg_by_entity(report_scope, rids)

    per_report_images: dict[int, list[dict]] = {}
    all_image_ids: list[int] = []
    for rid in rids:
        imgs = list_images(report_scope, rid)
        per_report_images[rid] = imgs
        all_image_ids.extend(int(i["id"]) for i in imgs)

    img_scores = scores_for(report_scope, all_image_ids, viewer)
    img_comments = comment_counts(image_scope, all_image_ids)

    for r in reports:
        rid = int(r["id"])
        imgs = per_report_images.get(rid, [])
        r["images"] = [_image_row(i, img_scores, img_comments) for i in imgs]
        r["photo_count"] = int(counts.get(rid, len(imgs)))
        r["comment_count"] = int(day_comments.get(rid, 0))
        sc = day_scores.get(rid)
        r["score_avg"] = sc["avg"] if sc else None
        r["score_count"] = sc["count"] if sc else 0


def _image_row(img: dict, img_scores: dict[int, dict], img_comments: dict[int, int]) -> dict:
    iid = int(img["id"])
    s = img_scores.get(iid)
    return {
        "id": iid,
        # điểm CHUNG của ảnh = trung bình các người đã chấm (mỗi người 1 điểm riêng)
        "score": s["score"] if s else None,
        "score_count": s["score_count"] if s else 0,      # bao nhiêu NGƯỜI đã chấm
        "my_score": s["my_score"] if s else None,         # điểm của chính người đang xem
        "raters": s["raters"] if s else [],               # [{by, score, at}] — ai cho mấy điểm
        "comment_count": int(img_comments.get(iid, 0)),
        # ai chụp + chụp lúc nào của CHÍNH bức ảnh này (entity_images.uploaded_by/
        # created_at, epoch giây UTC) — trang xem ảnh hiện "người chụp · giờ chụp".
        # Khác created_by/created_at của BÁO CÁO (người mở báo cáo ngày đó).
        "uploaded_by": str(img.get("uploaded_by") or ""),
        "created_at": int(img.get("created_at") or 0),
    }


def attach_today_scores(report_scope: str, rows: list[dict], today_report_ids: dict[int, int]) -> None:
    """Gắn today.score_avg/score_count cho hàng dashboard.
    today_report_ids = {entity_id (khu vực/thợ): report_id của HÔM NAY}."""
    if not today_report_ids:
        for row in rows:
            row["today"]["score_avg"] = None
            row["today"]["score_count"] = 0
        return
    scores = avg_by_entity(report_scope, list(today_report_ids.values()))
    for row in rows:
        rid = today_report_ids.get(int(row["id"]))
        sc = scores.get(rid) if rid else None
        row["today"]["score_avg"] = sc["avg"] if sc else None
        row["today"]["score_count"] = sc["count"] if sc else 0
