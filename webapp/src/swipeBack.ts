// Vuốt từ mép trái → quay lại, trang trượt theo ngón tay (như native).
// Dễ + mượt: mép rộng, ngưỡng thấp, nhận cả "flick" nhanh, cập nhật bằng rAF +
// tăng tốc GPU (translate3d/will-change). Bắt đầu sát mép trái → không đụng cuộn
// ngang bảng / carousel ảnh. Tắt khi mở PhotoViewer (body.pv-open). Không thư viện.
const EDGE = 40; // px từ mép trái — vùng bắt đầu vuốt (rộng cho dễ)
const MIN_DX = 55; // px ngang tối thiểu khi thả để "back"
const FLICK_DX = 24; // px tối thiểu nếu là flick nhanh
const FLICK_V = 0.45; // px/ms — vận tốc coi là flick
const MAX_DY = 60; // px dọc tối đa (lệch nhiều = cuộn dọc, bỏ)

function pageEl(): HTMLElement | null {
  return document.querySelector("main.page");
}

export function installSwipeBack(): void {
  let startX = 0;
  let startY = 0;
  let startT = 0;
  let dx = 0;
  let tracking = false;
  let raf = 0;
  let el: HTMLElement | null = null;

  const apply = () => {
    raf = 0;
    if (el) el.style.transform = `translate3d(${dx}px,0,0)`;
  };

  const reset = (withTransition: boolean) => {
    if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
    if (!el) return;
    el.style.transition = withTransition ? "transform .22s cubic-bezier(.22,.61,.36,1)" : "none";
    el.style.transform = "";
    el.style.boxShadow = "";
    el.style.willChange = "";
  };

  addEventListener(
    "touchstart",
    (e) => {
      tracking = false;
      if (e.touches.length !== 1 || document.body.classList.contains("pv-open")) return;
      const t = e.touches[0];
      startX = t.clientX;
      startY = t.clientY;
      startT = e.timeStamp;
      dx = 0;
      if (t.clientX > EDGE) return;
      tracking = true;
      el = pageEl();
      if (el) {
        el.style.transition = "none";
        el.style.willChange = "transform";
      }
    },
    { passive: true }
  );

  addEventListener(
    "touchmove",
    (e) => {
      if (!tracking || !el) return;
      const t = e.touches[0];
      dx = t.clientX - startX;
      const dy = Math.abs(t.clientY - startY);
      if (dy > MAX_DY && dx < 24) {
        tracking = false;
        reset(true);
        return;
      }
      if (dx < 0) dx = 0;
      el.style.boxShadow = dx > 4 ? "-10px 0 20px rgba(0,0,0,.14)" : "";
      if (!raf) raf = requestAnimationFrame(apply);
    },
    { passive: true }
  );

  addEventListener(
    "touchend",
    (e) => {
      if (!tracking || !el) return;
      tracking = false;
      const cur = el;
      const t = e.changedTouches[0];
      const finalDx = t.clientX - startX;
      const dy = Math.abs(t.clientY - startY);
      const dt = Math.max(1, e.timeStamp - startT);
      const v = finalDx / dt; // px/ms
      const go = dy < MAX_DY && (finalDx > MIN_DX || (finalDx > FLICK_DX && v > FLICK_V));
      if (raf) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
      if (go) {
        cur.style.transition = "transform .16s ease-out";
        cur.style.transform = "translate3d(100%,0,0)";
        let settled = false;
        const done = () => {
          if (settled) return;
          settled = true;
          cur.removeEventListener("transitionend", done);
          history.back();
          requestAnimationFrame(() => {
            cur.style.transition = "none";
            cur.style.transform = "";
            cur.style.boxShadow = "";
            cur.style.willChange = "";
          });
        };
        cur.addEventListener("transitionend", done);
        setTimeout(done, 240);
      } else {
        reset(true);
      }
    },
    { passive: true }
  );
}
