// Dải xem trước ảnh — thanh thumbnail ngang gọn (dưới nav nhanh của đơn). Bấm
// thumbnail mở lightbox; realtime tự tải lại. NHIỀU ảnh tràn màn → TỰ CUỘN vòng
// như banner, nhưng chạy bằng rAF trên scrollLeft (không phải CSS transform) để
// USER CUỘN TAY ĐƯỢC: chạm/cuộn → tạm dừng, yên ~3s → tự chạy tiếp từ chỗ đó;
// nhân đôi dãy + wrap scrollLeft theo độ rộng 1 dãy = vòng vô tận. Data: GET {base}/images.
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

  // CUỘN VÒNG bằng rAF trên scrollLeft — user chạm/cuộn tay thì DỪNG, yên 3s chạy tiếp
  useEffect(() => {
    const el = viewRef.current;
    if (!el || !rollW) return;
    const SPEED = 36;            // px/s — đều như banner
    const IDLE_MS = 3000;        // yên chừng này sau lần chạm cuối mới chạy lại
    let raf = 0, last = performance.now(), pausedUntil = 0;
    let pos = el.scrollLeft;
    let expected = pos;   // vị trí do MÌNH đặt — sự kiện scroll bắn ASYNC nên
                          // không dùng cờ được; phân biệt user bằng ĐỘ LỆCH
    const step = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (now >= pausedUntil) {
        pos += SPEED * dt;
        if (pos >= rollW) pos -= rollW;   // wrap = vòng vô tận (2 dãy giống nhau)
        expected = pos;
        el.scrollLeft = pos;
      } else {
        pos = el.scrollLeft;              // user đang kéo → theo vị trí thật
        expected = pos;
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    const touch = () => { pausedUntil = performance.now() + IDLE_MS; };
    // lệch nhiều so với vị trí mình đặt = user kéo/đà trượt → giữ dừng
    const onScroll = () => { if (Math.abs(el.scrollLeft - expected) > 2) touch(); };
    el.addEventListener("pointerdown", touch);
    el.addEventListener("touchstart", touch, { passive: true });
    el.addEventListener("wheel", touch, { passive: true });
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("pointerdown", touch);
      el.removeEventListener("touchstart", touch);
      el.removeEventListener("wheel", touch);
      el.removeEventListener("scroll", onScroll);
    };
  }, [rollW]);

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
        <div class="img-strip-roll">
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
