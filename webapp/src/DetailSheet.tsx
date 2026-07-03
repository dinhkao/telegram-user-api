// Bottom-sheet cho trang chi tiết: mở đè lên dashboard (dashboard mờ phía sau),
// trượt lên khi mở, vuốt xuống để đóng (như đóng ảnh ở PhotoViewer). Cuộn nội
// dung bên trong sheet; chỉ nhận vuốt-đóng khi đã cuộn lên đỉnh. Không thư viện.
import { useEffect, useRef } from "preact/hooks";

const CLOSE_DY = 120; // px kéo xuống tối thiểu để đóng
const FLICK_V = 0.5; // px/ms — vuốt nhanh cũng đóng

export function DetailSheet({ onClose, children }: { onClose: () => void; children: any }) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLDivElement>(null);
  const g = useRef({ startY: 0, startT: 0, dy: 0, dragging: false, closing: false, raf: 0 });

  const setBack = (o: number) => {
    if (backRef.current) backRef.current.style.opacity = String(o);
  };

  const animateClose = () => {
    const st = g.current;
    if (st.closing) return;
    st.closing = true;
    const s = sheetRef.current;
    if (s) {
      s.style.transition = "transform .24s ease-in";
      s.style.transform = "translateY(100%)";
    }
    if (backRef.current) backRef.current.style.transition = "opacity .24s";
    setBack(0);
    setTimeout(onClose, 220);
  };

  const snapBack = () => {
    const s = sheetRef.current;
    if (s) {
      s.style.transition = "transform .2s ease-out";
      s.style.transform = "translateY(0)";
    }
    if (backRef.current) backRef.current.style.transition = "opacity .2s";
    setBack(1);
    g.current.dy = 0;
  };

  // Enter animation + khoá cuộn nền + gắn touch (passive:false để preventDefault)
  useEffect(() => {
    const s = sheetRef.current;
    if (!s) return;
    document.body.classList.add("sheet-open");
    s.style.transform = "translateY(100%)";
    setBack(0);
    requestAnimationFrame(() => {
      s.style.transition = "transform .28s cubic-bezier(.22,.61,.36,1)";
      if (backRef.current) backRef.current.style.transition = "opacity .28s";
      s.style.transform = "translateY(0)";
      setBack(1);
    });

    const apply = () => {
      g.current.raf = 0;
      const dy = Math.max(0, g.current.dy);
      s.style.transform = `translateY(${dy}px)`;
      setBack(Math.max(0, 1 - dy / 500));
    };

    const onStart = (e: TouchEvent) => {
      if (e.touches.length !== 1 || g.current.closing) return;
      const st = g.current;
      st.startY = e.touches[0].clientY;
      st.startT = e.timeStamp;
      st.dy = 0;
      // chỉ cho kéo-đóng khi sheet đã cuộn lên đỉnh
      st.dragging = s.scrollTop <= 0;
      s.style.transition = "none";
      if (backRef.current) backRef.current.style.transition = "none";
    };
    const onMove = (e: TouchEvent) => {
      const st = g.current;
      if (!st.dragging) return;
      const dy = e.touches[0].clientY - st.startY;
      if (dy <= 0) {
        // đổi ý, cuộn lên → nhả kéo, trả về vị trí, để cuộn tự nhiên
        st.dragging = false;
        s.style.transform = "";
        setBack(1);
        return;
      }
      st.dy = dy;
      e.preventDefault(); // chặn cuộn khi đang kéo-đóng
      if (!st.raf) st.raf = requestAnimationFrame(apply);
    };
    const onEnd = (e: TouchEvent) => {
      const st = g.current;
      if (!st.dragging) return;
      st.dragging = false;
      if (st.raf) {
        cancelAnimationFrame(st.raf);
        st.raf = 0;
      }
      const dt = Math.max(1, e.timeStamp - st.startT);
      const v = st.dy / dt;
      if (st.dy > CLOSE_DY || (st.dy > 40 && v > FLICK_V)) animateClose();
      else snapBack();
    };

    s.addEventListener("touchstart", onStart, { passive: true });
    s.addEventListener("touchmove", onMove, { passive: false });
    s.addEventListener("touchend", onEnd, { passive: true });
    s.addEventListener("touchcancel", onEnd, { passive: true });
    return () => {
      document.body.classList.remove("sheet-open");
      s.removeEventListener("touchstart", onStart);
      s.removeEventListener("touchmove", onMove);
      s.removeEventListener("touchend", onEnd);
      s.removeEventListener("touchcancel", onEnd);
    };
  }, []);

  return (
    <>
      <div class="sheet-backdrop" ref={backRef} onClick={animateClose} />
      <div class="detail-sheet" ref={sheetRef}>
        <div class="sheet-handle" onClick={animateClose}>
          <span class="sheet-grip" />
        </div>
        {children}
      </div>
    </>
  );
}
