// Dải xem trước ảnh — thanh thumbnail ngang gọn (dưới nav nhanh của đơn). Bấm
// thumbnail mở lightbox; realtime tự tải lại. Data: GET {base}/images.
import { useEffect, useState } from "preact/hooks";
import { listMediaImages, mediaImageUrl, type OrderImage } from "../api";
import { onRealtime, eventMatchesBase } from "../realtime";
import { PhotoViewer } from "./PhotoViewer";
import { Icon } from "../ui/Icon";
import { isOrderBase, KIND_ICON, KIND_LABEL, kindOf } from "./imageKinds";

export function ImageStrip({ base, onCamera }: { base: string; onCamera?: () => void }) {
  const [images, setImages] = useState<OrderImage[]>([]);
  const [lightbox, setLightbox] = useState<OrderImage | null>(null);

  const load = async () => {
    try { setImages(await listMediaImages(base)); } catch { /* mất mạng → giữ nguyên */ }
  };
  useEffect(() => { load(); }, [base]);

  // Realtime: ảnh thêm/xoá trên cùng thực thể → tải lại dải
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (eventMatchesBase(base, e)) { clearTimeout(t); t = setTimeout(load, 300); }
    });
    return () => { clearTimeout(t); off(); };
  }, [base]);

  const order = isOrderBase(base);
  return (
    <div class="img-strip">
      {images.map((img) => (
        <button class="img-strip-tile" key={img.id} onClick={() => setLightbox(img)}>
          <img src={mediaImageUrl(base, img.id, "thumb")} loading="lazy" alt="" />
          {order && (
            <span class="img-strip-kind" title={KIND_LABEL[kindOf(img)]}>{KIND_ICON[kindOf(img)]} {KIND_LABEL[kindOf(img)]}</span>
          )}
        </button>
      ))}
      {onCamera && (
        <button class="img-strip-tile img-strip-cam" onClick={onCamera} title="Chụp ảnh"><Icon name="camera" size={20} /></button>
      )}
      {lightbox && (
        <PhotoViewer
          images={images}
          start={Math.max(0, images.findIndex((x) => x.id === lightbox.id))}
          base={base}
          editable={isOrderBase(base)}
          onKindChange={(id, kind) => setImages((prev) => prev.map((x) => (x.id === id ? { ...x, kind } : x)))}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
