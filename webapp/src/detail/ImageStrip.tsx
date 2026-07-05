// Dải xem trước ảnh — thanh thumbnail ngang gọn (dưới nav nhanh của đơn). Bấm
// thumbnail mở lightbox; realtime tự tải lại. Data: GET {base}/images.
import { useEffect, useState } from "preact/hooks";
import { listMediaImages, mediaImageUrl, type OrderImage } from "../api";
import { onRealtime, eventMatchesBase } from "../realtime";
import { PhotoViewer } from "./PhotoViewer";

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

  return (
    <div class="img-strip">
      {images.map((img) => (
        <button class="img-strip-tile" key={img.id} onClick={() => setLightbox(img)}>
          <img src={mediaImageUrl(base, img.id, "thumb")} loading="lazy" alt="" />
        </button>
      ))}
      {onCamera && (
        <button class="img-strip-tile img-strip-cam" onClick={onCamera} title="Chụp ảnh">📸</button>
      )}
      {lightbox && (
        <PhotoViewer
          images={images}
          start={Math.max(0, images.findIndex((x) => x.id === lightbox.id))}
          base={base}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
