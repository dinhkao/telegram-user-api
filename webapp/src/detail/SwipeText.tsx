// 1 dòng chữ cắt "…" như cũ nhưng KÉO NGANG được để đọc tiếp (card view Siêu gọn
// dashboard Đơn). Không thanh cuộn. Chromium không vẽ lại text-overflow:ellipsis khi
// phần tử cuộn (dấu "…" đứng yên, kéo tới cuối thì trống) → dùng dấu "…" GIẢ ghim mép
// phải, chỉ hiện khi bên phải còn chữ; nền "inherit" theo card (xong/vừa mở/nháy).
// Bật/tắt dấu bằng classList trên ref — không setState mỗi sự kiện cuộn.
import { useLayoutEffect, useRef } from "preact/hooks";
import type { ComponentChildren } from "preact";

export function SwipeText({ children, class: cls = "" }: { children: ComponentChildren; class?: string }) {
  const sc = useRef<HTMLSpanElement>(null);
  const box = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = sc.current, b = box.current;
    if (!el || !b) return;
    const upd = () => b.classList.toggle("more", el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
    upd();
    el.addEventListener("scroll", upd, { passive: true });
    const ro = new ResizeObserver(upd);
    ro.observe(el);
    return () => { el.removeEventListener("scroll", upd); ro.disconnect(); };
  });
  return (
    <span class={`swipe-text ${cls}`} ref={box}>
      <span class="swipe-text-sc" ref={sc}>{children}</span>
      <span class="swipe-text-more" aria-hidden="true">…</span>
    </span>
  );
}
