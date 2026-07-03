// Vuốt từ mép trái → quay lại, có hiệu ứng trang trượt theo ngón tay (như native).
// Chỉ nhận khi bắt đầu sát mép trái (≤ EDGE px) → không đụng cuộn ngang bảng /
// carousel ảnh. Tắt khi mở PhotoViewer (body.pv-open). Không thư viện.
//
// Cơ chế: kéo → dịch <main.page> sang phải theo ngón tay. Thả:
//   - qua ngưỡng → trượt hết ra + history.back() rồi reset (trang trước hiện).
//   - chưa đủ → trượt về chỗ cũ.
const EDGE = 30; // px từ mép trái — vùng bắt đầu vuốt
const MIN_DX = 80; // px ngang tối thiểu khi thả để tính "back"
const MAX_DY = 45; // px dọc tối đa (lệch nhiều = cuộn dọc, bỏ)

function pageEl(): HTMLElement | null {
  return document.querySelector("main.page");
}

export function installSwipeBack(): void {
  let startX = 0;
  let startY = 0;
  let dx = 0;
  let tracking = false;
  let el: HTMLElement | null = null;

  const clearStyle = (withTransition: boolean) => {
    if (!el) return;
    el.style.transition = withTransition ? "transform .2s ease-out" : "none";
    el.style.transform = "";
    el.style.boxShadow = "";
  };

  addEventListener(
    "touchstart",
    (e) => {
      tracking = false;
      if (e.touches.length !== 1 || document.body.classList.contains("pv-open")) return;
      const t = e.touches[0];
      startX = t.clientX;
      startY = t.clientY;
      dx = 0;
      if (t.clientX > EDGE) return;
      tracking = true;
      el = pageEl();
      if (el) el.style.transition = "none";
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
      // Lệch dọc rõ khi chưa kéo ngang → nhường cuộn dọc
      if (dy > MAX_DY && dx < 20) {
        tracking = false;
        clearStyle(true);
        return;
      }
      if (dx < 0) dx = 0;
      el.style.transform = `translateX(${dx}px)`;
      el.style.boxShadow = dx > 4 ? "-8px 0 16px rgba(0,0,0,.15)" : "";
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
      if (finalDx > MIN_DX && dy < MAX_DY) {
        // trượt hết ra rồi back + reset (trang trước hiện tại vị trí 0)
        cur.style.transition = "transform .18s ease-out";
        cur.style.transform = "translateX(100%)";
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
          });
        };
        cur.addEventListener("transitionend", done);
        // dự phòng nếu transitionend không bắn
        setTimeout(done, 260);
      } else {
        clearStyle(true);
      }
    },
    { passive: true }
  );
}
