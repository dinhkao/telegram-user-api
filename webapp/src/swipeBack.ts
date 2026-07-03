// Vuốt từ mép trái sang phải để quay lại (như back gesture Android/iOS).
// Chỉ nhận khi bắt đầu sát mép trái (≤ EDGE px) → không đụng cuộn ngang bảng /
// carousel ảnh. Tắt khi đang mở PhotoViewer (body.pv-open). Không thư viện.
const EDGE = 30; // px tính từ mép trái — vùng bắt đầu vuốt
const MIN_DX = 70; // px ngang tối thiểu để tính là "vuốt back"
const MAX_DY = 45; // px dọc tối đa (lệch nhiều = cuộn dọc, bỏ)

export function installSwipeBack(): void {
  let startX = 0;
  let startY = 0;
  let tracking = false;

  addEventListener(
    "touchstart",
    (e) => {
      if (e.touches.length !== 1 || document.body.classList.contains("pv-open")) {
        tracking = false;
        return;
      }
      const t = e.touches[0];
      startX = t.clientX;
      startY = t.clientY;
      tracking = t.clientX <= EDGE; // chỉ bắt đầu từ mép trái
    },
    { passive: true }
  );

  addEventListener(
    "touchend",
    (e) => {
      if (!tracking) return;
      tracking = false;
      const t = e.changedTouches[0];
      const dx = t.clientX - startX;
      const dy = Math.abs(t.clientY - startY);
      if (dx > MIN_DX && dy < MAX_DY) history.back();
    },
    { passive: true }
  );
}
