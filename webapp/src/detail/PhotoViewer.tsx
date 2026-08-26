// Xem ảnh phóng to — pinch-zoom + kéo (pan) + double-tap zoom + vuốt xuống đóng +
// vuốt trái/phải chuyển ảnh. Engine cử chỉ nằm ở detail/useImageGestures (DÙNG CHUNG
// với PhotoReportViewer — sửa cảm giác cử chỉ ở đó, đừng chép lại). Dùng bởi: detail/Images.
import { useEffect, useRef, useState } from "preact/hooks";
import { mediaImageUrl, type OrderImage } from "../api";
import { copyImageFromUrl } from "../copyImage";
import { fmtTime } from "../format";
import { toast } from "../ui/feedback";
import { ImageInfoPanel } from "./ImageInfoPanel";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { fastScrollLeft } from "../scroll";
import { useImageGestures } from "./useImageGestures";

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
  usePopupBack(true, onClose);   // back → đóng ảnh trước
  const [idx, setIdx] = useState(start);
  const [panelOpen, setPanelOpen] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const thumbsRef = useRef<HTMLDivElement>(null);
  const flash = (m: string, kind: "ok" | "err" | "info" = "info") => toast(m, kind);

  // Cử chỉ (pinch/pan/double-tap/vuốt) → hook dùng chung với PhotoReportViewer.
  // goRef: hook được tạo TRƯỚC go nhưng vẫn gọi được bản mới nhất.
  const goRef = useRef<(d: number) => void>(() => {});
  const { reset, handlers } = useImageGestures({
    imgRef, overlayRef,
    onPrev: () => goRef.current(-1),
    onNext: () => goRef.current(1),
    onClose,
    ignoreSelector: ".pv-controls, .pv-thumbs, .pv-topbar, .pv-panel",
    resetKey: idx,           // đổi ảnh → tự về 1× và canh giữa
  });

  // Đổi ảnh → cuộn dải thumbnail cho thumb đang xem vào giữa (zoom do hook reset)
  useEffect(() => {
    const strip = thumbsRef.current;
    const el = strip?.querySelector(".pv-thumb.active") as HTMLElement | null;
    if (strip && el) {
      const sr = strip.getBoundingClientRect();
      const er = el.getBoundingClientRect();
      const delta = er.left + er.width / 2 - (sr.left + sr.width / 2);
      fastScrollLeft(strip, strip.scrollLeft + delta);
    }
  }, [idx]);

  // Khoá cuộn nền (useScrollLock dùng chung, ref-count) + phím: Esc đóng, ← → chuyển ảnh
  useScrollLock(true);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") setIdx((i) => (i > 0 ? i - 1 : i));
      else if (e.key === "ArrowRight") setIdx((i) => (i < images.length - 1 ? i + 1 : i));
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [images.length]);

  const go = (d: number) => {
    const n = idx + d;
    if (n >= 0 && n < images.length) setIdx(n);
    else reset(true); // hết ảnh → bật lại
  };
  goRef.current = go;

  const cur = images[idx];

  // Copy ảnh vào clipboard — lõi dùng chung src/copyImage.ts (cầu native APK +
  // ClipboardItem PNG trình duyệt); ở đây chỉ còn thông báo.
  const copyImage = async () => {
    if (!cur) return;
    try {
      await copyImageFromUrl(mediaImageUrl(base, cur.id, "full"));
      flash("Đã copy ảnh", "ok");
    } catch {
      flash("Copy không được (trình duyệt chặn)", "err");
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
        flash(ok === false ? "Lưu ảnh lỗi" : "Đã lưu vào thư viện", ok === false ? "err" : "ok");
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
      flash("Đã tải ảnh", "ok");
    } catch (e: any) {
      if (e?.name === "AbortError") return; // người dùng đóng share sheet
      flash("Tải không được", "err");
    }
  };

  if (!cur) return null;

  return (
    <div
      class="pv-overlay"
      ref={overlayRef}
      onPointerDown={handlers.onPointerDown as any}
      onPointerMove={handlers.onPointerMove as any}
      onPointerUp={handlers.onPointerUp as any}
      onPointerCancel={handlers.onPointerCancel as any}
      onWheel={handlers.onWheel as any}
    >
      <img ref={imgRef} class="pv-img" src={mediaImageUrl(base, cur.id, "full")} draggable={false} alt="" />
      {(cur as any).deleted_at ? <span class="img-x-mark pv-x" title="Ảnh đã xoá" /> : null}

      {/* Thanh trên: loại+bình luận / copy / tải / đóng */}
      <div class="pv-topbar">
        {editable && (
          <button class={"pv-tbtn" + (panelOpen ? " on" : "")} title="Loại & bình luận" onClick={() => setPanelOpen((v) => !v)}><Icon name="chat" size={16} /></button>
        )}
        <button class="pv-tbtn" title="Copy ảnh" onClick={copyImage}><Icon name="copy" size={16} /></button>
        <button class="pv-tbtn" title="Tải / chia sẻ ảnh" onClick={downloadImage}><Icon name="download" size={16} /></button>
        <button class="pv-tbtn" title="Đóng" onClick={onClose}><Icon name="close" size={16} /></button>
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
              <button key={im.id} class={`pv-thumb${i === idx ? " active" : ""}${(im as any).deleted_at ? " img-deleted" : ""}`} onClick={() => setIdx(i)} aria-label={`Ảnh ${i + 1}`}>
                <img src={mediaImageUrl(base, im.id, "thumb")} loading="lazy" alt="" />
                {(im as any).deleted_at ? <span class="img-x-mark" /> : null}
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
