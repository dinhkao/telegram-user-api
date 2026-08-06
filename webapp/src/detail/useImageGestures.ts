// CỬ CHỈ XEM ẢNH dùng chung (Pointer Events + CSS transform, không thư viện):
// pinch-zoom · kéo (pan) khi đã phóng · double-tap zoom · vuốt trái/phải đổi ảnh ·
// vuốt xuống đóng · lăn chuột zoom. Tách từ detail/PhotoViewer (trình xem ảnh đơn
// hàng) để trình xem ảnh BÁO CÁO (PhotoReportViewer) dùng ĐÚNG một engine — sửa cảm
// giác cử chỉ ở đây là cả hai nơi cùng đổi, không chép lại.
//
// Mấu chốt để MƯỢT: mọi trạng thái nằm trong useRef và ghi thẳng vào style.transform,
// KHÔNG setState mỗi lần ngón di chuyển (setState mỗi frame = giật + zoom "nhảy").
import { useEffect, useRef } from "preact/hooks";
import type { RefObject } from "preact";

export const MIN_SCALE = 1;
export const MAX_SCALE = 8;
export const DOUBLE_TAP_SCALE = 2.5;
const SWIPE_X = 60;    // ngưỡng đổi ảnh (px)
const SWIPE_Y = 110;   // ngưỡng vuốt-xuống-đóng (px)

type Pt = { x: number; y: number };

export function useImageGestures({
  imgRef, overlayRef, onPrev, onNext, onClose, ignoreSelector, resetKey,
  dim = true, swipeClose = true, tapOutsideClose = true,
}: {
  imgRef: RefObject<HTMLImageElement>;
  overlayRef: RefObject<HTMLDivElement>;
  onPrev: () => void;                 // vuốt phải / ‹
  onNext: () => void;                 // vuốt trái / ›
  onClose: () => void;                // vuốt xuống / chạm nền ngoài ảnh
  ignoreSelector?: string;            // vùng KHÔNG bắt cử chỉ (nút, panel, dải thumb)
  resetKey?: unknown;                 // đổi (vd chỉ số ảnh) → về 1× và canh giữa
  dim?: boolean;                      // làm mờ nền khi vuốt xuống (trình xem full-screen)
  // Ảnh NHÚNG trong khung (không chiếm cả màn) thì tắt 2 cái dưới: vùng đen quanh
  // ảnh rất hẹp nên chạm/vuốt vào đó mà đóng cả trang là bấm nhầm liên tục.
  swipeClose?: boolean;               // vuốt xuống = đóng
  tapOutsideClose?: boolean;          // chạm nền ngoài ảnh = đóng
}) {
  const g = useRef({
    scale: 1, tx: 0, ty: 0,
    pointers: new Map<number, Pt>(),
    pinchDist: 0, pinchScale: 1, anchorX: 0, anchorY: 0,
    panX: 0, panY: 0, startX: 0, startY: 0,
    axis: "" as "" | "h" | "v",
    moved: false, lastTap: 0, lastTapX: 0, lastTapY: 0,
  });

  const apply = (animate = false) => {
    const im = imgRef.current;
    if (!im) return;
    im.style.transition = animate ? "transform .2s ease" : "none";
    const s = g.current;
    im.style.transform = `translate3d(${s.tx}px,${s.ty}px,0) scale(${s.scale})`;
    if (dim && overlayRef.current) {
      overlayRef.current.style.background =
        `rgba(0,0,0,${s.axis === "v" ? Math.max(0.4, 0.95 - Math.abs(s.ty) / 400) : 0.95})`;
    }
  };

  const reset = (animate = false) => {
    const s = g.current;
    s.scale = 1; s.tx = 0; s.ty = 0; s.axis = "";
    apply(animate);
  };

  useEffect(() => { reset(false); }, [resetKey]);   // eslint-disable-line

  // Toạ độ viewport → toạ độ ảnh (trước scale), tâm ảnh làm gốc
  const vpToImg = (px: number, py: number): Pt => {
    const r = imgRef.current!.getBoundingClientRect();
    const s = g.current;
    return { x: (px - (r.left + r.width / 2)) / s.scale, y: (py - (r.top + r.height / 2)) / s.scale };
  };

  const zoomAt = (newScale: number, vx: number, vy: number) => {
    const s = g.current;
    if (!imgRef.current) return;
    newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, newScale));
    if (newScale === s.scale) return;
    const r = imgRef.current.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const k = newScale / s.scale - 1;
    s.tx -= (vx - cx) * k;
    s.ty -= (vy - cy) * k;
    s.scale = newScale;
    apply();
  };

  const midOf = (): Pt & { d: number } => {
    const ids = [...g.current.pointers.values()];
    const a = ids[0], b = ids[1];
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, d: Math.hypot(a.x - b.x, a.y - b.y) };
  };

  const onPointerDown = (e: PointerEvent) => {
    if (ignoreSelector && (e.target as HTMLElement).closest(ignoreSelector)) return;
    overlayRef.current?.setPointerCapture(e.pointerId);
    const s = g.current;
    s.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (s.pointers.size === 2) {
      const m = midOf();
      s.pinchDist = m.d;
      s.pinchScale = s.scale;
      const a = vpToImg(m.x, m.y);
      s.anchorX = a.x; s.anchorY = a.y;
    } else if (s.pointers.size === 1) {
      s.panX = e.clientX; s.panY = e.clientY;
      s.startX = e.clientX; s.startY = e.clientY;
      s.axis = ""; s.moved = false;
      if (e.pointerType === "touch") {           // double-tap zoom
        const now = Date.now();
        if (now - s.lastTap < 300 && Math.hypot(e.clientX - s.lastTapX, e.clientY - s.lastTapY) < 30) {
          if (s.scale > 1.05) reset(true);
          else zoomAt(DOUBLE_TAP_SCALE, e.clientX, e.clientY);
          s.lastTap = 0;
        } else {
          s.lastTap = now; s.lastTapX = e.clientX; s.lastTapY = e.clientY;
        }
      }
    }
  };

  const onPointerMove = (e: PointerEvent) => {
    const s = g.current;
    if (!s.pointers.has(e.pointerId)) return;
    s.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (s.pointers.size >= 2) {                  // chụm 2 ngón
      const m = midOf();
      if (s.pinchDist > 0 && overlayRef.current) {
        const ns = Math.min(MAX_SCALE, Math.max(MIN_SCALE, s.pinchScale * (m.d / s.pinchDist)));
        const or = overlayRef.current.getBoundingClientRect();
        s.tx = m.x - (or.left + or.width / 2) - s.anchorX * ns;
        s.ty = m.y - (or.top + or.height / 2) - s.anchorY * ns;
        s.scale = ns;
        apply();
      }
      e.preventDefault();
      return;
    }
    if (s.scale > 1.01) {                        // đã phóng → kéo ảnh
      s.tx += e.clientX - s.panX;
      s.ty += e.clientY - s.panY;
      s.panX = e.clientX; s.panY = e.clientY;
      apply();
      e.preventDefault();
      return;
    }
    // chưa phóng → vuốt điều hướng / đóng (khoá trục để không vừa ngang vừa dọc)
    const dx = e.clientX - s.startX;
    const dy = e.clientY - s.startY;
    if (!s.axis && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
      s.axis = Math.abs(dx) > Math.abs(dy) ? "h" : "v";
      s.moved = true;
    }
    if (s.axis === "h") { s.tx = dx; s.ty = 0; apply(); e.preventDefault(); }
    else if (s.axis === "v") { s.ty = dy; s.tx = 0; apply(); e.preventDefault(); }
  };

  const onPointerUp = (e: PointerEvent) => {
    const s = g.current;
    if (!s.pointers.has(e.pointerId)) return;
    const wasSingle = s.pointers.size === 1;
    s.pointers.delete(e.pointerId);
    if (s.pointers.size < 2) s.pinchDist = 0;
    if (s.pointers.size === 1) {
      const p = [...s.pointers.values()][0];
      s.panX = p.x; s.panY = p.y;
      return;
    }
    if (s.pointers.size > 0) return;

    if (wasSingle && s.scale <= 1.01) {
      if (s.axis === "h") {
        if (s.tx > SWIPE_X) onPrev();
        else if (s.tx < -SWIPE_X) onNext();
        else reset(true);
      } else if (s.axis === "v") {
        if (swipeClose && s.ty > SWIPE_Y) onClose();
        else reset(true);
      } else if (!s.moved && tapOutsideClose) {
        // chạm nền (ngoài ảnh) → đóng; chạm lên ảnh → để double-tap lo zoom
        const r = imgRef.current?.getBoundingClientRect();
        if (!r || e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose();
      }
      return;
    }
    if (s.scale <= 1.01) reset(true);            // nhả pinch về ~1 → canh giữa lại
  };

  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    zoomAt(g.current.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX, e.clientY);
  };

  return {
    reset,
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp, onWheel },
  };
}
