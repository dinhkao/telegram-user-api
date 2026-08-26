// Trình xem 1 ẢNH từ URL bất kỳ (không thuộc gallery đơn) — dùng cho ảnh render
// on-the-fly như PNG hoá đơn điện tử VNPT. Cử chỉ (pinch/pan/double-tap/vuốt
// xuống đóng) dùng chung useImageGestures — CẤM chép lại logic cử chỉ.
// CSS dùng nguyên bộ .pv-* của PhotoViewer.
import { useRef, useState } from "preact/hooks";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { useImageGestures } from "./useImageGestures";

export function SingleImageViewer({ src, title, onClose }: {
  src: string;
  title?: string;      // dòng chữ nhỏ khi đang tải (ảnh render mất 1-2s)
  onClose: () => void;
}) {
  usePopupBack(true, onClose);
  useScrollLock(true);
  const imgRef = useRef<HTMLImageElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState(false);
  const { handlers } = useImageGestures({
    imgRef, overlayRef, onPrev: () => {}, onNext: () => {}, onClose,
    ignoreSelector: ".pv-topbar",
  });
  return (
    <div class="pv-overlay" ref={overlayRef}
      onPointerDown={handlers.onPointerDown as any}
      onPointerMove={handlers.onPointerMove as any}
      onPointerUp={handlers.onPointerUp as any}
      onPointerCancel={handlers.onPointerCancel as any}
      onWheel={handlers.onWheel as any}>
      {!loaded && !err && (
        <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#bbb;font-size:.85rem">
          Đang tải {title || "ảnh"}…
        </div>
      )}
      {err && (
        <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#f88;font-size:.85rem">
          Lỗi tải ảnh — đóng rồi thử lại
        </div>
      )}
      <img ref={imgRef} class="pv-img" src={src} draggable={false} alt=""
        style={loaded ? undefined : "visibility:hidden"}
        onLoad={() => setLoaded(true)} onError={() => setErr(true)} />
      <div class="pv-topbar">
        <button class="pv-tbtn" title="Đóng" onClick={onClose}><Icon name="close" size={16} /></button>
      </div>
    </div>
  );
}
