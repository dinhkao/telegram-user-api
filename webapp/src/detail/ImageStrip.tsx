// Dải xem trước ảnh — thanh thumbnail ngang gọn (dưới nav nhanh của đơn). Bấm
// thumbnail mở lightbox; realtime tự tải lại. NHIỀU ảnh tràn màn → TỰ CUỘN vòng
// (marquee) như banner đầu app: nhân đôi dãy + translateX(-50%) loop, tốc độ
// px/s ổn định theo độ rộng. Data: GET {base}/images.
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
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

  // đo tràn: dãy 1 bản rộng hơn chỗ chứa → bật cuộn vòng (đo lại khi images đổi)
  const viewRef = useRef<HTMLDivElement>(null);
  const [rollW, setRollW] = useState(0);   // 0 = tĩnh; >0 = độ rộng 1 dãy (px)
  useLayoutEffect(() => {
    const el = viewRef.current;
    if (!el) return;
    const one = el.querySelector<HTMLElement>(".img-strip-set");
    const w = one ? one.scrollWidth : 0;
    setRollW(w > el.clientWidth + 4 ? w : 0);
  }, [images.length]);

  const tiles = (dup: string) => images.map((img) => (
    <button class={"img-strip-tile" + ((img as any).deleted_at ? " img-deleted" : "")} key={`${dup}${img.id}`} onClick={() => setLightbox(img)}>
      <img src={mediaImageUrl(base, img.id, "thumb")} loading="lazy" alt="" />
      {(img as any).deleted_at ? <span class="img-x-mark" /> : null}
      {order && (
        <span class="img-strip-kind" title={KIND_LABEL[kindOf(img)]}>{KIND_ICON[kindOf(img)]} {KIND_LABEL[kindOf(img)]}</span>
      )}
    </button>
  ));

  return (
    <div class="img-strip">
      <div class={"img-strip-view" + (rollW ? " rolling" : "")} ref={viewRef}>
        <div class="img-strip-roll" style={rollW ? { animationDuration: `${Math.max(8, Math.round((rollW / 36) * 10) / 10)}s` } : undefined}>
          <span class="img-strip-set">{tiles("a")}</span>
          {rollW ? <span class="img-strip-set">{tiles("b")}</span> : null}
        </div>
      </div>
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
