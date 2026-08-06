// Xem 1 ẢNH báo cáo phóng to + CHẤM ĐIỂM 0–10 + TRAO ĐỔI riêng của bức ảnh đó.
// Dùng chung cho vệ sinh khu vực (#/khu-vuc/:id) và chất lượng mâm kẹo
// (#/chat-luong/:id) — điểm lưu theo scope BÁO CÁO (…/images/{id}/score), bình luận
// theo scope ẢNH (media scope area_image/quality_image, entity_id = image_id).
// Bố cục: thanh trên · KHUNG ẢNH · rồi CHẤM ĐIỂM + TRAO ĐỔI hiện thẳng bên dưới
// (cuộn trong .prv-scroll) — KHÔNG giấu sau nút.
// Đầu trang hiện TÊN (thợ / khu vực) · NGƯỜI CHỤP · GIỜ CHỤP (giờ VN) của bức ảnh.
// ⚠ Cử chỉ ảnh (pinch-zoom · kéo · double-tap · vuốt trái/phải đổi ảnh) lấy từ hook
// dùng chung detail/useImageGestures — cùng engine với trình xem ảnh đơn hàng, đừng
// viết lại. Ở đây ảnh NHÚNG trong khung nên tắt vuốt-xuống-đóng và chạm-nền-đóng.
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
  const imgRef = useRef<HTMLImageElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const goRef = useRef<(d: number) => void>(() => {});
  const { reset, handlers } = useImageGestures({
    imgRef, overlayRef: stageRef,
    onPrev: () => goRef.current(-1),
    onNext: () => goRef.current(1),
    onClose,
    ignoreSelector: ".prv-nav",  // nút ‹ › nằm TRONG khung → đừng nuốt cú bấm
    resetKey: index,             // đổi ảnh → tự về 1× và canh giữa
    dim: false,                  // ảnh nhúng trong khung, không phủ cả màn
    swipeClose: false,           // khung hẹp → vuốt xuống KHÔNG đóng (dễ bấm nhầm)
    tapOutsideClose: false,      // chạm viền đen cũng không đóng — đã có nút ✕
  });
  const go = (d: number) => {
    const n = index + d;
    if (n >= 0 && n < images.length) onIndex(n);
    else reset(true);
  };
  goRef.current = go;

  const img = images[index];
  if (!img) return null;
  const base = `/api/media/${scope.report}/${entityId}`;

  const doScore = async (n: number) => {
    setBusy(true);
    try {
      // bấm lại đúng số MÌNH đang chọn = bỏ điểm CỦA MÌNH (điểm người khác giữ nguyên)
      if (img.my_score === n) { await clearImageScore(scope.report, entityId, img.id); toast("Đã bỏ điểm của bạn", "ok"); }
      else { await setImageScore(scope.report, entityId, img.id, n); toast(`✅ Bạn chấm ${n}/10`, "ok"); }
      onChanged();
    } catch (e: any) { toast(e?.message || "Lỗi chấm điểm", "err"); }
    finally { setBusy(false); }
  };

  // Ảnh cũ (lưu trước khi có uploaded_by/created_at) → lùi về thông tin của báo cáo
  const taker = img.uploaded_by && img.uploaded_by !== "?" ? img.uploaded_by : (reportBy || "");
  const takenAt = fmtHourVN(img.created_at || reportAt || "");

  return (
    <div class="prv-overlay">
      <div class="prv-bar">
        <button class="prv-x" onClick={onClose} title="Đóng"><Icon name="close" size={20} /></button>
        <span class="prv-title">{dayLabel(ymd)} · ảnh {index + 1}/{images.length}</span>
      </div>

      {/* Ai · chụp lúc mấy giờ — thông tin của CHÍNH bức ảnh đang xem */}
      <div class="prv-meta">
        {subject ? (
          <span class="prv-meta-i"><Icon name="user" size={13} />
            <span class="muted">{subjectLabel}:</span> <b>{subject}</b></span>
        ) : null}
        {taker ? (
          <span class="prv-meta-i"><Icon name="camera" size={13} />
            <span class="muted">Người chụp:</span> <b>{taker}</b></span>
        ) : null}
        {takenAt ? (
          <span class="prv-meta-i"><Icon name="clock" size={13} />
            <span class="muted">Lúc</span> <b>{takenAt}</b></span>
        ) : null}
      </div>

      <div class="prv-stage" ref={stageRef}
        onPointerDown={handlers.onPointerDown as any}
        onPointerMove={handlers.onPointerMove as any}
        onPointerUp={handlers.onPointerUp as any}
        onPointerCancel={handlers.onPointerCancel as any}
        onWheel={handlers.onWheel as any}>
        {images.length > 1 && (
          <button class="prv-nav left" disabled={index === 0}
            onClick={() => go(-1)} title="Ảnh trước">‹</button>
        )}
        <img ref={imgRef} class="prv-img" alt="" draggable={false}
          src={mediaImageUrl(base, img.id, "full")} />
        {images.length > 1 && (
          <button class="prv-nav right" disabled={index === images.length - 1}
            onClick={() => go(1)} title="Ảnh sau">›</button>
        )}
      </div>

      <div class="prv-scroll">
        <section class="card prv-score">
          <div class="row space">
            <b>Điểm của bạn</b>
            <span class={"prv-score-now " + scoreClass(img.my_score)}>
              {img.my_score == null ? "bạn chưa chấm" : `${img.my_score}/10`}
            </span>
          </div>
          <div class="prv-chips">
            {SCORES.map((n) => (
              <button key={n} disabled={busy}
                class={"prv-chip " + (img.my_score === n ? "on " + scoreClass(n) : "")}
                onClick={() => doScore(n)}>{n}</button>
            ))}
          </div>
          <p class="muted small" style={{ margin: "6px 0 0" }}>
            {img.my_score == null
              ? "Bấm 1 số để chấm (0 = rất kém, 10 = rất tốt). Mỗi người chấm điểm riêng."
              : "Bấm lại đúng số đang chọn để bỏ điểm của bạn."}
          </p>

          {/* Điểm CHUNG + ai cho mấy điểm — mỗi người một điểm riêng */}
          {img.score_count > 0 && (
            <div class="prv-raters">
              <div class="row space">
                <span class="muted small">Trung bình {img.score_count} người chấm</span>
                <span class={"prv-score-now " + scoreClass(img.score)}>{img.score}/10</span>
              </div>
              <div class="prv-rater-list">
                {img.raters.map((r) => (
                  <span class="prv-rater" key={r.by}>
                    {r.by || "?"} <b class={scoreClass(r.score)}>{r.score}</b>
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Trao đổi RIÊNG của bức ảnh này (scope ảnh, entity = image_id) */}
        <Comments base={`/api/media/${scope.image}/${img.id}`} allowPin={false} />
      </div>
    </div>
  );
}
