// Cuộn NHANH tự viết (~240ms easeOutCubic) dùng CHUNG toàn app — thay
// behavior:"smooth" mặc định (chậm/khựng trên mobile). Cuộn tức thời (không
// animate) thì cứ dùng window.scrollTo(x,y) như thường; util này CHỈ cho cuộn
// có hiệu ứng. Dùng bởi: OrderDetail, History, ProductionDetail, SoanHangPicker,
// OrdersList, PhotoViewer…
const DUR = 240;
const EASE = (p: number) => 1 - Math.pow(1 - p, 3); // easeOutCubic

/** Cuộn window (dọc) tới Y với hiệu ứng nhanh. */
export function fastScrollY(target: number, dur = DUR): void {
  const start = window.scrollY;
  const dist = target - start;
  if (Math.abs(dist) < 2) { window.scrollTo(0, Math.max(0, target)); return; }
  const t0 = performance.now();
  const step = (now: number) => {
    const p = Math.min(1, (now - t0) / dur);
    window.scrollTo(0, start + dist * EASE(p));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Lên đầu trang (nhanh). */
export function fastScrollTop(): void {
  fastScrollY(0);
}

/** Cuộn 1 phần tử vào GIỮA (mặc định) hoặc gần ĐỈNH màn hình (nhanh). */
export function fastScrollToEl(el: Element, block: "center" | "start" = "center"): void {
  const rect = el.getBoundingClientRect();
  const start = window.scrollY;
  const target = block === "start"
    ? start + rect.top - 56
    : start + rect.top - Math.max(56, (window.innerHeight - rect.height) / 2);
  fastScrollY(target);
}

/** Cuộn NGANG 1 container tới scrollLeft (nhanh) — cho dải thumbnail… */
export function fastScrollLeft(el: Element, target: number, dur = DUR): void {
  const start = el.scrollLeft;
  const dist = target - start;
  if (Math.abs(dist) < 2) { el.scrollLeft = target; return; }
  const t0 = performance.now();
  const step = (now: number) => {
    const p = Math.min(1, (now - t0) / dur);
    el.scrollLeft = start + dist * EASE(p);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
