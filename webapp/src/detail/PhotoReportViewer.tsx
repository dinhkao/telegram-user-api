// Xem 1 ẢNH báo cáo phóng to + CHẤM ĐIỂM 0–10 + TRAO ĐỔI riêng của bức ảnh đó.
// Dùng chung cho vệ sinh khu vực (#/khu-vuc/:id) và chất lượng mâm kẹo
// (#/chat-luong/:id) — điểm lưu theo scope BÁO CÁO (…/images/{id}/score), bình luận
// theo scope ẢNH (media scope area_image/quality_image, entity_id = image_id).
// Lướt ‹ › giữa các ảnh trong cùng ngày. Nối: api.setImageScore/clearImageScore, Comments.
import { useState } from "preact/hooks";
import {
  mediaImageUrl, setImageScore, clearImageScore,
  type PhotoScope, type ReportImage,
} from "../api";
import { dayLabel } from "../format";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Comments } from "./Comments";

/** Màu theo thang điểm: ≥8 tốt · 5–7 tạm · <5 kém. */
export function scoreClass(n: number | null | undefined): string {
  if (n == null) return "";
  return n >= 8 ? "t-ok" : n >= 5 ? "t-warn" : "t-danger";
}

const SCORES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

export function PhotoReportViewer({
  scope, entityId, ymd, images, index, onIndex, onClose, onChanged,
}: {
  scope: PhotoScope;
  entityId: number;              // id BÁO CÁO (1 ngày) chứa ảnh
  ymd: string;
  images: ReportImage[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
  onChanged: () => void;         // tải lại trang cha sau khi chấm/bỏ điểm
}) {
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const img = images[index];
  if (!img) return null;
  const base = `/api/media/${scope.report}/${entityId}`;

  const doScore = async (n: number) => {
    setBusy(true);
    try {
      if (img.score === n) { await clearImageScore(scope.report, entityId, img.id); toast("Đã bỏ điểm", "ok"); }
      else { await setImageScore(scope.report, entityId, img.id, n); toast(`✅ Đã chấm ${n}/10`, "ok"); }
      onChanged();
    } catch (e: any) { toast(e?.message || "Lỗi chấm điểm", "err"); }
    finally { setBusy(false); }
  };

  return (
    <div class="prv-overlay">
      <div class="prv-bar">
        <button class="prv-x" onClick={onClose} title="Đóng"><Icon name="close" size={20} /></button>
        <span class="prv-title">{dayLabel(ymd)} · ảnh {index + 1}/{images.length}</span>
      </div>

      <div class="prv-stage">
        {images.length > 1 && (
          <button class="prv-nav left" disabled={index === 0}
            onClick={() => onIndex(index - 1)} title="Ảnh trước">‹</button>
        )}
        <img class="prv-img" alt="" src={mediaImageUrl(base, img.id, "full")} />
        {images.length > 1 && (
          <button class="prv-nav right" disabled={index === images.length - 1}
            onClick={() => onIndex(index + 1)} title="Ảnh sau">›</button>
        )}
      </div>

      <div class="prv-scroll">
        <section class="card prv-score">
          <div class="row space">
            <b>Chấm điểm ảnh này</b>
            <span class={"prv-score-now " + scoreClass(img.score)}>
              {img.score == null ? "chưa chấm" : `${img.score}/10`}
            </span>
          </div>
          <div class="prv-chips">
            {SCORES.map((n) => (
              <button key={n} disabled={busy}
                class={"prv-chip " + (img.score === n ? "on " + scoreClass(n) : "")}
                onClick={() => doScore(n)}>{n}</button>
            ))}
          </div>
          <p class="muted small" style={{ margin: "6px 0 0" }}>
            {img.score == null
              ? "Bấm 1 số để chấm (0 = rất kém, 10 = rất tốt)."
              : (img.scored_by && img.scored_by !== "?"
                ? `${img.scored_by} chấm · bấm lại đúng số đang chọn để bỏ điểm`
                : "Bấm lại đúng số đang chọn để bỏ điểm.")}
          </p>
        </section>

        {/* Trao đổi RIÊNG của bức ảnh này (scope ảnh, entity = image_id) */}
        <Comments base={`/api/media/${scope.image}/${img.id}`} allowPin={false} />
      </div>
    </div>
  );
}
