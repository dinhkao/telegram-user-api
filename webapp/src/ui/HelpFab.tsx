// Nút TRỢ GIÚP nổi (floating) hiện MỌI trang — KÉO ĐƯỢC để đổi chỗ (nhớ vị trí),
// bấm mở trang Hướng dẫn (#/huong-dan), thỉnh thoảng NHÚN để người dùng thấy.
// Mount 1 lần ở main.tsx (trong .app). Ẩn khi có popup (body.modal-open, CSS).
import { useEffect, useRef, useState } from "preact/hooks";

const LS_KEY = "help_fab_pos";
const SIZE = 52;          // đường kính nút (khớp CSS)
const MARGIN = 8;         // lề tối thiểu với mép màn
const MOVE_THRESHOLD = 6; // px: quá ngưỡng = kéo (không tính là bấm)

type Pos = { x: number; y: number };

function clampPos(p: Pos): Pos {
  const maxX = Math.max(MARGIN, window.innerWidth - SIZE - MARGIN);
  const maxY = Math.max(MARGIN, window.innerHeight - SIZE - MARGIN);
  return {
    x: Math.min(Math.max(MARGIN, p.x), maxX),
    y: Math.min(Math.max(MARGIN, p.y), maxY),
  };
}

function defaultPos(): Pos {
  // Góc phải, phía trên thanh điều hướng đáy.
  return clampPos({ x: window.innerWidth - SIZE - 14, y: window.innerHeight - SIZE - 96 });
}

function loadPos(): Pos {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (typeof p?.x === "number" && typeof p?.y === "number") return clampPos(p);
    }
  } catch { /* hỏng → mặc định */ }
  return defaultPos();
}

export function HelpFab() {
  const [pos, setPos] = useState<Pos>(loadPos);
  const [dragging, setDragging] = useState(false);
  const [wiggle, setWiggle] = useState(false);
  const posRef = useRef(pos);
  posRef.current = pos;
  // true ngay sau khi KÉO → nuốt sự kiện click kèm theo (không điều hướng).
  const suppressClick = useRef(false);
  const drag = useRef<{ sx: number; sy: number; bx: number; by: number; moved: boolean; id: number } | null>(null);

  // Nhún định kỳ để gây chú ý (bỏ qua khi đang kéo).
  useEffect(() => {
    const t = setInterval(() => {
      if (drag.current) return;
      setWiggle(true);
      setTimeout(() => setWiggle(false), 1150);
    }, 9000);
    return () => clearInterval(t);
  }, []);

  // Giữ nút trong màn khi xoay/đổi cỡ.
  useEffect(() => {
    const onResize = () => setPos((p) => clampPos(p));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const onDown = (e: any) => {
    const el = e.currentTarget as HTMLElement;
    try { el.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    drag.current = { sx: e.clientX, sy: e.clientY, bx: pos.x, by: pos.y, moved: false, id: e.pointerId };
    setDragging(true);
    setWiggle(false);
  };
  const onMove = (e: any) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.sx, dy = e.clientY - d.sy;
    if (!d.moved && Math.hypot(dx, dy) > MOVE_THRESHOLD) d.moved = true;
    if (d.moved) {
      const np = clampPos({ x: d.bx + dx, y: d.by + dy });
      posRef.current = np;
      setPos(np);
    }
  };
  const endDrag = (e: any) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    setDragging(false);
    if (d.moved) {
      // Nuốt ĐÚNG cú click tổng hợp ngay sau khi kéo; tự bỏ cờ sau 300ms để không
      // nuốt nhầm cú bấm hợp lệ tiếp theo (phòng khi trình duyệt không bắn click).
      suppressClick.current = true;
      setTimeout(() => { suppressClick.current = false; }, 300);
      try { localStorage.setItem(LS_KEY, JSON.stringify(posRef.current)); } catch { /* ignore */ }
    }
  };
  const onClick = () => {
    if (suppressClick.current) return;
    // Truyền trang đang xem (bỏ query) → trang Hướng dẫn lọc bài liên quan lên đầu.
    const from = (window.location.hash || "").split("?")[0];
    window.location.hash = "#/huong-dan?from=" + encodeURIComponent(from);
  };

  return (
    <button
      class={"help-fab" + (dragging ? " dragging" : "") + (wiggle && !dragging ? " wiggle" : "")}
      style={{ left: pos.x + "px", top: pos.y + "px" }}
      title="Hướng dẫn — kéo để di chuyển"
      aria-label="Mở hướng dẫn sử dụng"
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onClick={onClick}
    >
      <span class="hf-q" aria-hidden="true">?</span>
    </button>
  );
}
