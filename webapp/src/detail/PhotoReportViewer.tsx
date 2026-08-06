// Xem 1 ẢNH báo cáo phóng to + CHẤM ĐIỂM 0–10 + TRAO ĐỔI riêng của bức ảnh đó.
// Dùng chung cho vệ sinh khu vực (#/khu-vuc/:id) và chất lượng mâm kẹo
// (#/chat-luong/:id) — điểm lưu theo scope BÁO CÁO (…/images/{id}/score), bình luận
// theo scope ẢNH (media scope area_image/quality_image, entity_id = image_id).
// Đầu trang hiện TÊN (thợ / khu vực) · NGƯỜI CHỤP · GIỜ CHỤP (giờ VN) của bức ảnh.
// Thao tác ảnh: chụm 2 ngón hoặc chạm 2 lần để ZOOM, kéo để rê khi đã zoom,
// VUỐT trái/phải để sang ảnh trước/sau (chỉ khi chưa zoom); phím ← → cũng chạy.
// Nối: api.setImageScore/clearImageScore, Comments.
import { useEffect, useRef, useState } from "preact/hooks";
import {
  mediaImageUrl, setImageScore, clearImageScore,
  type PhotoScope, type ReportImage,
} from "../api";
import { dayLabel, fmtHourVN } from "../format";
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
const MAX_ZOOM = 4;
const SWIPE_PX = 55;          // kéo ngang quá ngần này (chưa zoom) = sang ảnh khác

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
  reportBy?: string;             // người mở báo cáo — dự phòng khi ảnh cũ chưa có uploaded_by
  reportAt?: string | number;
}) {
  const [busy, setBusy] = useState(false);
  const [z, setZ] = useState({ s: 1, x: 0, y: 0 });   // scale + dịch ảnh
  const [drag, setDrag] = useState(0);                // dịch ngang khi đang vuốt (chưa zoom)
  const stageRef = useRef<HTMLDivElement>(null);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const img = images[index];
  const canPrev = index > 0;
  const canNext = index < images.length - 1;

  const go = (i: number) => {
    if (i < 0 || i > images.length - 1) return;
    setZ({ s: 1, x: 0, y: 0 });                       // ảnh mới luôn về zoom 1x
    setDrag(0);
    onIndex(i);
  };

  // Phím ← → sang ảnh, Esc đóng (bàn phím trên máy tính)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") go(index - 1);
      else if (e.key === "ArrowRight") go(index + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, images.length]);

  // ── Cử chỉ: 1 ngón = vuốt/rê · 2 ngón = chụm zoom · chạm 2 lần = zoom nhanh ──
  const pts = useRef(new Map<number, { x: number; y: number }>());
  const start = useRef({ s: 1, x: 0, y: 0, dist: 0, cx: 0, cy: 0, px: 0, py: 0, moved: false });
  const lastTap = useRef(0);

  const dist2 = () => {
    const [a, b] = [...pts.current.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };
  const mid2 = () => {
    const [a, b] = [...pts.current.values()];
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  };

  const onDown = (e: PointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    start.current = {
      ...start.current, s: z.s, x: z.x, y: z.y,
      px: e.clientX, py: e.clientY, moved: false,
    };
    if (pts.current.size === 2) {
      const m = mid2();
      start.current.dist = dist2();
      start.current.cx = m.x; start.current.cy = m.y;
    }
  };

  const onMove = (e: PointerEvent) => {
    if (!pts.current.has(e.pointerId)) return;
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (pts.current.size >= 2) {                       // chụm 2 ngón → zoom quanh tâm
      const d = dist2();
      if (start.current.dist > 0) {
        const s = Math.min(MAX_ZOOM, Math.max(1, start.current.s * (d / start.current.dist)));
        const k = s / start.current.s;
        setZ({
          s,
          x: start.current.cx - (start.current.cx - start.current.x) * k,
          y: start.current.cy - (start.current.cy - start.current.y) * k,
        });
      }
      start.current.moved = true;
      return;
    }

    const dx = e.clientX - start.current.px;
    const dy = e.clientY - start.current.py;
    if (Math.abs(dx) > 6 || Math.abs(dy) > 6) start.current.moved = true;

    if (z.s > 1) setZ({ s: z.s, x: start.current.x + dx, y: start.current.y + dy });  // rê ảnh
    else setDrag(dx);                                                                 // vuốt sang ảnh
  };

  const onUp = (e: PointerEvent) => {
    pts.current.delete(e.pointerId);
    if (pts.current.size > 0) return;

    if (z.s <= 1) {
      const dx = drag;
      setDrag(0);
      if (dx <= -SWIPE_PX && canNext) { go(index + 1); return; }
      if (dx >= SWIPE_PX && canPrev) { go(index - 1); return; }
    }
    if (!start.current.moved) {                        // chạm 2 lần nhanh = zoom
      const now = Date.now();
      if (now - lastTap.current < 300) {
        lastTap.current = 0;
        setZ(z.s > 1 ? { s: 1, x: 0, y: 0 } : { s: 2.5, x: 0, y: 0 });
      } else lastTap.current = now;
    }
  };

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

  // Ảnh cũ (trước khi lưu uploaded_by/created_at) → lùi về thông tin của báo cáo ngày đó
  const taker = img.uploaded_by && img.uploaded_by !== "?" ? img.uploaded_by : (reportBy || "");
  const takenAt = fmtHourVN(img.created_at || reportAt || "");

  return (
    <div class="prv-overlay">
      <div class="prv-bar">
        <button class="prv-x" onClick={onClose} title="Đóng"><Icon name="close" size={20} /></button>
        <span class="prv-title">{dayLabel(ymd)} · ảnh {index + 1}/{images.length}</span>
        {z.s > 1 && (
          <button class="prv-zoomx" onClick={() => setZ({ s: 1, x: 0, y: 0 })}
            title="Về cỡ vừa màn hình">{z.s.toFixed(1)}× ✕</button>
        )}
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
            <span class="muted">Lúc</span> <b>{takenAt}</b> <span class="muted">{dayLabel(ymd)}</span></span>
        ) : null}
      </div>

      <div class="prv-stage" ref={stageRef}
        onPointerDown={onDown} onPointerMove={onMove}
        onPointerUp={onUp} onPointerCancel={onUp}>
        {images.length > 1 && (
          <button class="prv-nav left" disabled={!canPrev}
            onClick={() => go(index - 1)} title="Ảnh trước">‹</button>
        )}
        <img class={"prv-img" + (z.s > 1 ? " zoomed" : "")} alt=""
          draggable={false}
          style={{
            transform: `translate(${z.x + drag}px, ${z.y}px) scale(${z.s})`,
            transition: pts.current.size ? "none" : "transform .18s ease-out",
          }}
          src={mediaImageUrl(base, img.id, "full")} />
        {images.length > 1 && (
          <button class="prv-nav right" disabled={!canNext}
            onClick={() => go(index + 1)} title="Ảnh sau">›</button>
        )}
      </div>
      <p class="prv-hint muted small">
        {images.length > 1 ? "Vuốt trái/phải để xem ảnh khác · " : ""}chụm 2 ngón hoặc chạm 2 lần để phóng to
      </p>

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
