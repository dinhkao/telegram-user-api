// Xem 1 ẢNH báo cáo phóng to + CHẤM ĐIỂM 0–10 + TRAO ĐỔI riêng của bức ảnh đó.
// Dùng chung cho vệ sinh khu vực (#/khu-vuc/:id) và chất lượng mâm kẹo
// (#/chat-luong/:id) — điểm lưu theo scope BÁO CÁO (…/images/{id}/score), bình luận
// theo scope ẢNH (media scope area_image/quality_image, entity_id = image_id).
//
// KHUNG + CỬ CHỈ dùng ĐÚNG bộ của trình xem ảnh đơn hàng: CSS .pv-* và hook
// detail/useImageGestures (pinch-zoom, kéo, double-tap, vuốt trái/phải đổi ảnh,
// vuốt xuống đóng, lăn chuột zoom) — KHÔNG tự viết lại cử chỉ ở đây.
// Thanh dưới hiện: tên thợ/khu vực · NGƯỜI CHỤP · GIỜ CHỤP (giờ VN) của đúng bức ảnh.
// Chấm điểm + trao đổi nằm trong tấm trượt .pv-panel (bấm nút 💬 ở thanh trên).
import { useRef, useState } from "preact/hooks";
import {
  mediaImageUrl, setImageScore, clearImageScore,
  type PhotoScope, type ReportImage,
} from "../api";
import { dayLabel, fmtHourVN } from "../format";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { useImageGestures } from "./useImageGestures";
import { Comments } from "./Comments";

/** Màu theo thang điểm: ≥8 tốt · 5–7 tạm · <5 kém. */
export function scoreClass(n: number | null | undefined): string {
  if (n == null) return "";
  return n >= 8 ? "t-ok" : n >= 5 ? "t-warn" : "t-danger";
}

const SCORES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

export function PhotoReportViewer({
  scope, entityId, ymd, images, index, onIndex, onClose, onChanged,
  subject, subjectLabel = "Nhân viên", reportBy, reportAt,
}: {
  scope: PhotoScope;
  entityId: number;              // id BÁO CÁO (1 ngày) chứa ảnh
  ymd: string;
  images: ReportImage[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
  onChanged: () => void;         // tải lại trang cha sau khi chấm/bỏ điểm
  subject?: string;              // tên thợ (chất lượng mâm) / tên khu vực (vệ sinh)
  subjectLabel?: string;
  reportBy?: string;             // ảnh cũ chưa có uploaded_by → lùi về thông tin báo cáo
  reportAt?: string | number;
}) {
  const [busy, setBusy] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const goRef = useRef<(d: number) => void>(() => {});
  const { reset, handlers } = useImageGestures({
    imgRef, overlayRef,
    onPrev: () => goRef.current(-1),
    onNext: () => goRef.current(1),
    onClose,
    ignoreSelector: ".pv-controls, .pv-thumbs, .pv-topbar, .pv-panel",
    resetKey: index,
  });
  const go = (d: number) => {
    const n = index + d;
    if (n >= 0 && n < images.length) onIndex(n);
    else reset(true);            // hết ảnh → bật lại cho biết là biên
  };
  goRef.current = go;

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

  // Ảnh cũ (lưu trước khi có uploaded_by/created_at) → lùi về thông tin của báo cáo
  const taker = img.uploaded_by && img.uploaded_by !== "?" ? img.uploaded_by : (reportBy || "");
  const takenAt = fmtHourVN(img.created_at || reportAt || "");

  return (
    <div class="pv-overlay" ref={overlayRef}
      onPointerDown={handlers.onPointerDown as any}
      onPointerMove={handlers.onPointerMove as any}
      onPointerUp={handlers.onPointerUp as any}
      onPointerCancel={handlers.onPointerCancel as any}
      onWheel={handlers.onWheel as any}>

      <img ref={imgRef} class="pv-img" alt="" draggable={false}
        src={mediaImageUrl(base, img.id, "full")} />

      <div class="pv-topbar">
        <button class={"pv-tbtn" + (panelOpen ? " on" : "")} title="Chấm điểm & trao đổi"
          onClick={() => setPanelOpen((v) => !v)}>
          <Icon name="star" size={16} />
        </button>
        <button class="pv-tbtn" title="Đóng" onClick={onClose}><Icon name="close" size={16} /></button>
      </div>

      {/* Chấm điểm + trao đổi của RIÊNG bức ảnh này (tấm trượt dưới, tự cuộn) */}
      {panelOpen && (
        <div class="pv-panel prv-panel">
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
          <div class="prv-panel-scroll">
            <Comments base={`/api/media/${scope.image}/${img.id}`} allowPin={false} />
          </div>
        </div>
      )}

      {/* Dải thumbnail các ảnh cùng ngày — chạm để nhảy thẳng tới ảnh đó */}
      {images.length > 1 && (
        <div class="pv-thumbs">
          <div class="pv-thumbs-inner">
            {images.map((im, i) => (
              <button key={im.id} class={"pv-thumb" + (i === index ? " active" : "")}
                onClick={() => onIndex(i)} aria-label={`Ảnh ${i + 1}`}>
                <img src={mediaImageUrl(base, im.id, "thumb")} loading="lazy" alt="" />
                {im.score != null && (
                  <span class={"prd-score-tag " + scoreClass(im.score)}>{im.score}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      <div class="pv-controls">
        <span class="pv-info">
          {images.length > 1 ? `${index + 1}/${images.length} · ` : ""}
          {subject ? `${subjectLabel}: ${subject} · ` : ""}
          {taker ? `${taker} · ` : ""}{takenAt ? `${takenAt} ` : ""}{dayLabel(ymd)}
        </span>
        {/* Luôn render ‹ › (disable ở biên) để thanh không nhảy khi đổi ảnh */}
        <button class="btn" disabled={images.length <= 1 || index === 0} onClick={() => go(-1)}>‹</button>
        <button class="btn" disabled={images.length <= 1 || index === images.length - 1}
          onClick={() => go(1)}>›</button>
      </div>
    </div>
  );
}
