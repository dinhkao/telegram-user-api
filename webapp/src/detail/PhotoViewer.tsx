// Xem ảnh phóng to — chuyển thể từ new-task-app (Pointer Events + CSS transform,
// không thư viện): pinch-zoom + kéo (pan) + double-tap zoom. Thêm: vuốt xuống để
// đóng, vuốt trái/phải để chuyển ảnh. Dùng bởi: detail/Images.
import { useEffect, useRef, useState } from "preact/hooks";
import { mediaImageUrl, type OrderImage } from "../api";
import { fmtTime } from "../format";
import { toast } from "../ui/feedback";
import { ImageInfoPanel } from "./ImageInfoPanel";

const MIN_SCALE = 1;
const MAX_SCALE = 8;
const DOUBLE_TAP_SCALE = 2.5;
const SWIPE_X = 60; // ngưỡng đổi ảnh (px)
const SWIPE_Y = 110; // ngưỡng vuốt-xuống-đóng (px)

type Pt = { x: number; y: number };

export function PhotoViewer({
  images,
  start,
  base,
  editable,
  onKindChange,
  onClose,
}: {
  images: OrderImage[];
  start: number;
  base: string;
  editable?: boolean;                                   // ảnh đơn → cho đổi loại + bình luận
  onKindChange?: (id: number, kind: string) => void;
  onClose: () => void;
}) {
  const [idx, setIdx] = useState(start);
  const [panelOpen, setPanelOpen] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const thumbsRef = useRef<HTMLDivElement>(null);
  const flash = (m: string) => toast(m, "info");

  // Trạng thái biến đổi + cử chỉ giữ trong ref (không re-render mỗi frame)
  const g = useRef({
    scale: 1,
    tx: 0,
    ty: 0,
    pointers: new Map<number, Pt>(),
    pinchDist: 0,
    pinchScale: 1,
    anchorX: 0,
    anchorY: 0,
    panX: 0,
    panY: 0,
    startX: 0,
    startY: 0,
    axis: "" as "" | "h" | "v",
    moved: false,
    lastTap: 0,
    lastTapX: 0,
    lastTapY: 0,
  });

  const apply = (animate = false) => {
    const im = imgRef.current;
    if (!im) return;
    im.style.transition = animate ? "transform .2s ease" : "none";
    const s = g.current;
    im.style.transform = `translate3d(${s.tx}px,${s.ty}px,0) scale(${s.scale})`;
    if (overlayRef.current) overlayRef.current.style.background = `rgba(0,0,0,${s.axis === "v" ? Math.max(0.4, 0.95 - Math.abs(s.ty) / 400) : 0.95})`;
  };
  const reset = (animate = false) => {
    const s = g.current;
    s.scale = 1;
    s.tx = 0;
    s.ty = 0;
    s.axis = "";
    apply(animate);
  };

  // Đổi ảnh → về mặc định + cuộn dải thumbnail cho thumb đang xem vào giữa
  useEffect(() => {
    reset(false);
    const strip = thumbsRef.current;
    const el = strip?.querySelector(".pv-thumb.active") as HTMLElement | null;
    if (strip && el) {
      const sr = strip.getBoundingClientRect();
      const er = el.getBoundingClientRect();
      const delta = er.left + er.width / 2 - (sr.left + sr.width / 2);
      strip.scrollTo({ left: strip.scrollLeft + delta, behavior: "smooth" });
    }
  }, [idx]);

  // Khoá cuộn nền + phím: Esc đóng, ← → chuyển ảnh (desktop)
  useEffect(() => {
    document.body.classList.add("pv-open");
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") setIdx((i) => (i > 0 ? i - 1 : i));
      else if (e.key === "ArrowRight") setIdx((i) => (i < images.length - 1 ? i + 1 : i));
    };
    window.addEventListener("keydown", h);
    return () => {
      document.body.classList.remove("pv-open");
      window.removeEventListener("keydown", h);
    };
  }, [images.length]);

  const go = (d: number) => {
    const n = idx + d;
    if (n >= 0 && n < images.length) setIdx(n);
    else reset(true); // hết ảnh → bật lại
  };

  // Toạ độ viewport → toạ độ ảnh (trước scale), tâm ảnh làm gốc
  const vpToImg = (px: number, py: number): Pt => {
    const r = imgRef.current!.getBoundingClientRect();
    const s = g.current;
    return { x: (px - (r.left + r.width / 2)) / s.scale, y: (py - (r.top + r.height / 2)) / s.scale };
  };
  const zoomAt = (newScale: number, vx: number, vy: number) => {
    const s = g.current;
    newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, newScale));
    if (newScale === s.scale) return;
    const r = imgRef.current!.getBoundingClientRect();
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
    const a = ids[0];
    const b = ids[1];
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, d: Math.hypot(a.x - b.x, a.y - b.y) };
  };

  const onDown = (e: PointerEvent) => {
    if ((e.target as HTMLElement).closest(".pv-controls, .pv-thumbs, .pv-topbar, .pv-panel")) return; // để nút/thumbnail/panel bấm được
    overlayRef.current?.setPointerCapture(e.pointerId);
    const s = g.current;
    s.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (s.pointers.size === 2) {
      const m = midOf();
      s.pinchDist = m.d;
      s.pinchScale = s.scale;
      const a = vpToImg(m.x, m.y);
      s.anchorX = a.x;
      s.anchorY = a.y;
    } else if (s.pointers.size === 1) {
      s.panX = e.clientX;
      s.panY = e.clientY;
      s.startX = e.clientX;
      s.startY = e.clientY;
      s.axis = "";
      s.moved = false;
      // double-tap (chạm)
      if (e.pointerType === "touch") {
        const now = Date.now();
        if (now - s.lastTap < 300 && Math.hypot(e.clientX - s.lastTapX, e.clientY - s.lastTapY) < 30) {
          if (s.scale > 1.05) reset(true);
          else zoomAt(DOUBLE_TAP_SCALE, e.clientX, e.clientY);
          s.lastTap = 0;
        } else {
          s.lastTap = now;
          s.lastTapX = e.clientX;
          s.lastTapY = e.clientY;
        }
      }
    }
  };

  const onMove = (e: PointerEvent) => {
    const s = g.current;
    if (!s.pointers.has(e.pointerId)) return;
    s.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (s.pointers.size >= 2) {
      const m = midOf();
      if (s.pinchDist > 0) {
        const ns = Math.min(MAX_SCALE, Math.max(MIN_SCALE, s.pinchScale * (m.d / s.pinchDist)));
        const or = overlayRef.current!.getBoundingClientRect();
        s.tx = m.x - (or.left + or.width / 2) - s.anchorX * ns;
        s.ty = m.y - (or.top + or.height / 2) - s.anchorY * ns;
        s.scale = ns;
        apply();
      }
      e.preventDefault();
      return;
    }
    // 1 ngón
    if (s.scale > 1.01) {
      // đã phóng to → kéo ảnh
      s.tx += e.clientX - s.panX;
      s.ty += e.clientY - s.panY;
      s.panX = e.clientX;
      s.panY = e.clientY;
      apply();
      e.preventDefault();
      return;
    }
    // chưa phóng to → vuốt điều hướng / đóng
    const dx = e.clientX - s.startX;
    const dy = e.clientY - s.startY;
    if (!s.axis && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
      s.axis = Math.abs(dx) > Math.abs(dy) ? "h" : "v";
      s.moved = true;
    }
    if (s.axis === "h") {
      s.tx = dx;
      s.ty = 0;
      apply();
      e.preventDefault();
    } else if (s.axis === "v") {
      s.ty = dy;
      s.tx = 0;
      apply();
      e.preventDefault();
    }
  };

  const onUp = (e: PointerEvent) => {
    const s = g.current;
    if (!s.pointers.has(e.pointerId)) return;
    const wasSingle = s.pointers.size === 1;
    s.pointers.delete(e.pointerId);
    if (s.pointers.size < 2) s.pinchDist = 0;
    if (s.pointers.size === 1) {
      const p = [...s.pointers.values()][0];
      s.panX = p.x;
      s.panY = p.y;
      return;
    }
    if (s.pointers.size > 0) return;

    // Kết thúc cử chỉ 1 ngón khi chưa phóng to
    if (wasSingle && s.scale <= 1.01) {
      if (s.axis === "h") {
        if (s.tx > SWIPE_X) go(-1);
        else if (s.tx < -SWIPE_X) go(1);
        else reset(true);
      } else if (s.axis === "v") {
        if (s.ty > SWIPE_Y) onClose();
        else reset(true);
      } else if (!s.moved) {
        // chạm nền (ngoài ảnh) → đóng; chạm lên ảnh → bỏ qua (double-tap lo zoom)
        const r = imgRef.current?.getBoundingClientRect();
        if (!r || e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose();
      }
      return;
    }
    // vừa nhả pinch mà về ~1 → canh giữa lại
    if (s.scale <= 1.01) reset(true);
  };

  const cur = images[idx];

  // Copy ảnh vào clipboard (đổi sang PNG vì clipboard chỉ chắc ăn với PNG).
  // ClipboardItem nhận Promise → hợp lệ cả Safari (yêu cầu tạo trong cùng cử chỉ).
  const copyImage = async () => {
    if (!cur) return;
    try {
      const res = await fetch(mediaImageUrl(base, cur.id, "full"));
      const blob = await res.blob();
      // WebView Android không copy ảnh được → ưu tiên cầu native copyImage.
      const bridge: any = (window as any).AndroidApp;
      if (bridge?.copyImage) {
        const dataUrl: string = await new Promise((ok, no) => {
          const fr = new FileReader();
          fr.onload = () => ok(String(fr.result));
          fr.onerror = () => no(new Error("read"));
          fr.readAsDataURL(blob);
        });
        const ok = bridge.copyImage(dataUrl);
        flash(ok === false ? "Copy ảnh lỗi" : "✓ Đã copy ảnh");
        return;
      }
      // Trình duyệt: clipboard.write PNG (cần HTTPS)
      const bmp = await createImageBitmap(blob);
      const c = document.createElement("canvas");
      c.width = bmp.width;
      c.height = bmp.height;
      c.getContext("2d")!.drawImage(bmp, 0, 0);
      bmp.close?.();
      const png = await new Promise<Blob>((ok, no) => c.toBlob((b) => (b ? ok(b) : no(new Error("png"))), "image/png"));
      await navigator.clipboard.write([new (window as any).ClipboardItem({ "image/png": png })]);
      flash("✓ Đã copy ảnh");
    } catch {
      flash("Copy không được (trình duyệt chặn)");
    }
  };

  // Tải/chia sẻ ảnh. Trong WebView Android, <a download>/blob KHÔNG tải được
  // (không có DownloadListener native) → ưu tiên Web Share (mở share sheet: Lưu
  // ảnh / Photos / Zalo…). Trình duyệt desktop: rớt về tải file trực tiếp.
  const downloadImage = async () => {
    if (!cur) return;
    try {
      const res = await fetch(mediaImageUrl(base, cur.id, "full"));
      const blob = await res.blob();
      const ext = blob.type.includes("png") ? "png" : blob.type.includes("jpeg") ? "jpg" : blob.type.includes("webp") ? "webp" : "img";
      const name = `anh-${cur.id}.${ext}`;

      // Ưu tiên cầu native APK: lưu THẲNG vào thư viện ảnh (Photos) qua MediaStore.
      const bridge: any = (window as any).AndroidApp;
      if (bridge?.saveImage) {
        const dataUrl: string = await new Promise((res, rej) => {
          const fr = new FileReader();
          fr.onload = () => res(String(fr.result));
          fr.onerror = () => rej(new Error("read"));
          fr.readAsDataURL(blob);
        });
        const ok = bridge.saveImage(dataUrl, name);
        flash(ok === false ? "Lưu ảnh lỗi" : "✓ Đã lưu vào thư viện");
        return;
      }

      const nav: any = navigator;
      const file = new File([blob], name, { type: blob.type || "image/webp" });
      if (nav.canShare && nav.canShare({ files: [file] })) {
        await nav.share({ files: [file], title: name }); // share sheet có "Lưu ảnh"
        return; // sheet tự báo; không cần toast
      }
      // Fallback (desktop): tải trực tiếp
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      flash("✓ Đã tải ảnh");
    } catch (e: any) {
      if (e?.name === "AbortError") return; // người dùng đóng share sheet
      flash("Tải không được");
    }
  };

  if (!cur) return null;

  return (
    <div
      class="pv-overlay"
      ref={overlayRef}
      onPointerDown={onDown as any}
      onPointerMove={onMove as any}
      onPointerUp={onUp as any}
      onPointerCancel={onUp as any}
      onWheel={(e: any) => {
        e.preventDefault();
        zoomAt(g.current.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX, e.clientY);
      }}
    >
      <img ref={imgRef} class="pv-img" src={mediaImageUrl(base, cur.id, "full")} draggable={false} alt="" />

      {/* Thanh trên: loại+bình luận / copy / tải / đóng */}
      <div class="pv-topbar">
        {editable && (
          <button class={"pv-tbtn" + (panelOpen ? " on" : "")} title="Loại & bình luận" onClick={() => setPanelOpen((v) => !v)}>💬</button>
        )}
        <button class="pv-tbtn" title="Copy ảnh" onClick={copyImage}>⧉</button>
        <button class="pv-tbtn" title="Tải / chia sẻ ảnh" onClick={downloadImage}>⤓</button>
        <button class="pv-tbtn" title="Đóng" onClick={onClose}>✕</button>
      </div>

      {/* Bảng loại + bình luận ảnh (chỉ ảnh đơn) */}
      {editable && panelOpen && (
        <ImageInfoPanel base={base} image={cur} onKindChange={onKindChange} />
      )}

      {/* Dải thumbnail các ảnh cùng đơn — chạm để nhảy, cuộn ngang, tô sáng ảnh đang xem */}
      {images.length > 1 ? (
        <div class="pv-thumbs" ref={thumbsRef}>
          <div class="pv-thumbs-inner">
            {images.map((im, i) => (
              <button key={im.id} class={`pv-thumb${i === idx ? " active" : ""}`} onClick={() => setIdx(i)} aria-label={`Ảnh ${i + 1}`}>
                <img src={mediaImageUrl(base, im.id, "thumb")} loading="lazy" alt="" />
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div class="pv-controls">
        <span class="pv-info">
          {images.length > 1 ? `${idx + 1}/${images.length} · ` : ""}
          {cur.uploaded_by} · {fmtTime(cur.created_at)}
        </span>
        {/* Luôn render ‹ › (disable ở biên) để số nút KHÔNG đổi → thanh không nhảy */}
        <button class="btn" disabled={images.length <= 1 || idx === 0} onClick={() => go(-1)}>‹</button>
        <button class="btn" disabled={images.length <= 1 || idx === images.length - 1} onClick={() => go(1)}>›</button>
      </div>
    </div>
  );
}
