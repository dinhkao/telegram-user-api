// Vuốt mép trái → quay lại, thấy "sneak peek" trang trước bên dưới (như native).
// Không đổi router: chụp innerHTML trang đang rời (ảnh tĩnh) rồi đặt làm lớp dưới
// khi vuốt, có parallax (trang trước lệch trái rồi về giữa). Trang hiện tại đục,
// trượt theo ngón để lộ lớp dưới. Thả qua ngưỡng/flick → history.back().
// Tắt khi mở PhotoViewer. Không thư viện.
const EDGE = 40;
const MIN_DX = 55;
const FLICK_DX = 24;
const FLICK_V = 0.45;
const MAX_DY = 60;
const PARA = 0.25; // độ lệch trái của trang dưới (parallax)

function pageEl(): HTMLElement | null {
  return document.querySelector("main.page");
}

// Ảnh chụp trang vừa rời (để hiện bên dưới khi vuốt back).
let snapHtml: string | null = null;
let curHash = typeof location !== "undefined" ? location.hash : "";

export function installSwipeBack(): void {
  // Đăng ký TRƯỚC useHash của App (module load chạy trước render) → khi hashchange
  // bắn, DOM vẫn là trang cũ → chụp được trang đang rời.
  addEventListener("hashchange", () => {
    const leaving = pageEl();
    if (leaving) snapHtml = leaving.innerHTML;
    curHash = location.hash;
  });

  let startX = 0;
  let startY = 0;
  let startT = 0;
  let dx = 0;
  let w = 0;
  let tracking = false;
  let raf = 0;
  let el: HTMLElement | null = null;
  let under: HTMLElement | null = null;

  const removeUnder = (node: HTMLElement | null = under) => {
    if (node && node.parentNode) node.parentNode.removeChild(node);
    if (under === node) under = null;
  };

  const resetEl = (node: HTMLElement | null = el) => {
    if (!node) return;
    node.style.transition = "";
    node.style.transform = "";
    node.style.boxShadow = "";
    node.style.willChange = "";
    node.style.position = "";
    node.style.zIndex = "";
    node.style.background = "";
  };

  const apply = () => {
    raf = 0;
    if (el) el.style.transform = `translate3d(${dx}px,0,0)`;
    if (under) under.style.transform = `translate3d(${-PARA * (w - dx)}px,0,0)`;
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
      if (!el) return;
      w = window.innerWidth || el.getBoundingClientRect().width;
      // trang hiện tại: đục + nổi lên trên
      el.style.transition = "none";
      el.style.willChange = "transform";
      el.style.position = "relative";
      el.style.zIndex = "2";
      el.style.background = getComputedStyle(document.body).backgroundColor || "#fff";
      // lớp dưới = ảnh chụp trang trước
      if (snapHtml) {
        const r = el.getBoundingClientRect();
        under = document.createElement("div");
        under.className = "page swipe-underlay";
        under.innerHTML = snapHtml;
        Object.assign(under.style, {
          position: "fixed",
          top: `${r.top}px`,
          left: "0",
          width: `${r.width}px`,
          height: `${r.height}px`,
          overflow: "hidden",
          zIndex: "1",
          transform: `translate3d(${-PARA * w}px,0,0)`,
          background: getComputedStyle(document.body).backgroundColor || "#fff",
        } as CSSStyleDeclaration);
        el.parentNode?.insertBefore(under, el);
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
        removeUnder();
        el.style.transition = "transform .2s ease-out";
        el.style.transform = "";
        resetEl();
        return;
      }
      if (dx < 0) dx = 0;
      el.style.boxShadow = dx > 4 ? "-10px 0 20px rgba(0,0,0,.18)" : "";
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
      const un = under;
      const t = e.changedTouches[0];
      const finalDx = t.clientX - startX;
      const dy = Math.abs(t.clientY - startY);
      const dt = Math.max(1, e.timeStamp - startT);
      const v = finalDx / dt;
      const go = dy < MAX_DY && (finalDx > MIN_DX || (finalDx > FLICK_DX && v > FLICK_V));
      if (raf) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
      const ease = "transform .18s ease-out";
      cur.style.transition = ease;
      if (un) un.style.transition = ease;
      if (go) {
        cur.style.transform = "translate3d(100%,0,0)";
        if (un) un.style.transform = "translate3d(0,0,0)";
        let settled = false;
        const done = () => {
          if (settled) return;
          settled = true;
          cur.removeEventListener("transitionend", done);
          history.back();
          requestAnimationFrame(() => {
            removeUnder(un);
            resetEl(cur);
          });
        };
        cur.addEventListener("transitionend", done);
        setTimeout(done, 240);
      } else {
        // trượt về chỗ cũ
        cur.style.transform = "";
        if (un) un.style.transform = `translate3d(${-PARA * w}px,0,0)`;
        let settled = false;
        const done = () => {
          if (settled) return;
          settled = true;
          cur.removeEventListener("transitionend", done);
          removeUnder(un);
          resetEl(cur);
        };
        cur.addEventListener("transitionend", done);
        setTimeout(done, 240);
      }
    },
    { passive: true }
  );
}
