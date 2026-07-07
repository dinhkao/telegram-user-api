// Popup SẮP THỨ TỰ thợ trong bảng báo cáo — mở từ nút ⚙️ ở trang sửa báo cáo.
// KÉO tay (grip ≡, pointer-events → chạy cả cảm ứng lẫn chuột) hoặc bấm ↑↓ để đổi chỗ;
// "Áp dụng" → trả thứ tự MỚI cho trang (áp vào bảng) + lưu bền sort_order thợ toàn cục
// (reorderWorkers) để lần sau template seed đúng thứ tự.
// Neo đỉnh (sp-overlay/sp-sheet), usePopupBack + useScrollLock như mọi popup.
import { useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";

export function WorkerOrderPopup({
  open, names, onClose, onApply,
}: {
  open: boolean;
  names: string[];                 // thứ tự thợ hiện tại trong bảng (đã lọc rỗng)
  onClose: () => void;
  onApply: (order: string[]) => void;
}) {
  const [list, setList] = useState<string[]>(names);
  const [drag, setDrag] = useState<number | null>(null);   // dòng đang kéo (để tô sáng)
  const dragRef = useRef<number | null>(null);             // bản đồng bộ cho pointermove
  const rowRefs = useRef<(HTMLElement | null)[]>([]);
  useScrollLock(open);
  usePopupBack(open, onClose);
  // Mở lại → seed lại từ bảng hiện tại (names đổi giữa các lần mở)
  const [seed, setSeed] = useState<string[]>(names);
  if (open && seed !== names) { setSeed(names); setList(names); }
  if (!open) return null;

  const move = (i: number, d: -1 | 1) => setList((l) => {
    const j = i + d;
    if (j < 0 || j >= l.length) return l;
    const n = l.slice();
    [n[i], n[j]] = [n[j], n[i]];
    return n;
  });

  // ── Kéo tay: grip bắt pointer (setPointerCapture) → mọi move/up về grip đó.
  // pointermove: tìm dòng dưới ngón theo trung điểm rect → dời item tới đó (live).
  const onGripDown = (i: number) => (e: any) => {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    dragRef.current = i; setDrag(i);
  };
  const onGripMove = (e: any) => {
    const from = dragRef.current;
    if (from == null) return;
    const y = e.clientY;
    const rects = rowRefs.current.map((el) => el?.getBoundingClientRect());
    let to = rects.length - 1;
    for (let k = 0; k < rects.length; k++) {
      const r = rects[k];
      if (r && y < r.top + r.height / 2) { to = k; break; }
    }
    if (to === from) return;
    setList((l) => {
      const n = l.slice();
      const [it] = n.splice(from, 1);
      n.splice(to, 0, it);
      return n;
    });
    dragRef.current = to; setDrag(to);
  };
  const onGripUp = () => { dragRef.current = null; setDrag(null); };

  const apply = () => { onApply(list); onClose(); };

  return createPortal(
    <div class="sp-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="sp-sheet">
        <div class="sp-title"><Icon name="users" size={16} /> Sắp thứ tự thợ</div>
        <div class="sp-list wo-list">
          {list.length === 0 && <div class="muted small" style="padding:14px 16px">Chưa có thợ nào trong bảng.</div>}
          {list.map((nm, i) => (
            <div class={"wo-row" + (drag === i ? " dragging" : "")} key={nm + i}
              ref={(el: any) => { rowRefs.current[i] = el; }}>
              <span class="wo-grip" title="Kéo để đổi chỗ"
                onPointerDown={onGripDown(i)} onPointerMove={onGripMove}
                onPointerUp={onGripUp} onPointerCancel={onGripUp}>
                <Icon name="menu" size={18} />
              </span>
              <span class="wo-idx">{i + 1}</span>
              <span class="wo-name">{nm}</span>
              <button class="btn small wo-mv" disabled={i === 0} title="Lên" onClick={() => move(i, -1)}><Icon name="chevronDown" class="wo-up" size={16} /></button>
              <button class="btn small wo-mv" disabled={i === list.length - 1} title="Xuống" onClick={() => move(i, 1)}><Icon name="chevronDown" size={16} /></button>
            </div>
          ))}
        </div>
        <div class="wo-foot">
          <button class="btn" onClick={onClose}>Đóng</button>
          <button class="btn primary" disabled={list.length === 0} onClick={apply}><Icon name="check" size={16} /> Áp dụng</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
