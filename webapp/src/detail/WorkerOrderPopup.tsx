// Popup SẮP THỨ TỰ thợ trong bảng báo cáo — mở từ nút ⚙️ ở trang sửa báo cáo.
// KÉO tay (grip ≡, pointer-events → cảm ứng+chuột) hoặc bấm ↑↓ để đổi chỗ; "Áp dụng"
// → trả thứ tự MỚI cho trang (áp vào bảng) + lưu bền sort_order thợ toàn cục.
// Kéo = THẢ NỔI dòng đang giữ (translateY theo ngón), các dòng KHÁC TRƯỢT ±1 hàng để
// mở khe (transition CSS → mượt kiểu iOS); CHỈ dời list thật khi nhả tay → không splice
// mỗi frame (khỏi lag) và không remount dòng đang giữ (key theo id bền).
// Neo đỉnh (sp-overlay/sp-sheet), usePopupBack + useScrollLock như mọi popup.
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";

type Item = { id: number; name: string };
const toItems = (names: string[]): Item[] => names.map((name, id) => ({ id, name }));

export function WorkerOrderPopup({
  open, names, onClose, onApply,
}: {
  open: boolean;
  names: string[];                 // thứ tự thợ hiện tại trong bảng (đã lọc rỗng)
  onClose: () => void;
  onApply: (order: string[]) => void;
}) {
  const [list, setList] = useState<Item[]>(() => toItems(names));
  // trạng thái kéo (dùng ref để pointermove khỏi phụ thuộc closure cũ)
  const [dragIdx, setDragIdx] = useState<number | null>(null);   // dòng đang kéo (vị trí gốc)
  const [dropTo, setDropTo] = useState<number>(0);               // sẽ chèn TRƯỚC index này (0..len)
  const [dy, setDy] = useState(0);                               // lệch Y để thả nổi
  const [rowH, setRowH] = useState(0);                           // cao 1 hàng (đo lúc grab) → dịch khe
  const [settling, setSettling] = useState(false);              // đang GLIDE về chỗ sau khi nhả
  const dragRef = useRef<number | null>(null);
  const dropRef = useRef<number>(0);               // chỗ chèn HIỆN TẠI (đọc lúc nhả, khỏi stale)
  const midsRef = useRef<number[]>([]);            // trung điểm Y GỐC mỗi hàng (chốt lúc grab)
  const startY = useRef(0);
  const rowRefs = useRef<(HTMLElement | null)[]>([]);
  useScrollLock(open);
  usePopupBack(open, onClose);
  // Seed CHỈ lúc mở (open false→true) — KHÔNG mỗi render, vì `names` là mảng mới
  // mỗi lần cha render → nếu seed theo tham chiếu sẽ ghi đè mọi lần đổi chỗ.
  useEffect(() => { if (open) setList(toItems(names)); }, [open]);   // eslint-disable-line
  if (!open) return null;

  const swap = (i: number, d: -1 | 1) => setList((l) => {
    const j = i + d;
    if (j < 0 || j >= l.length) return l;
    const n = l.slice();
    [n[i], n[j]] = [n[j], n[i]];
    return n;
  });

  // ── Kéo: grip bắt pointer → mọi move/up về grip đó. KHÔNG dời list khi kéo, chỉ
  // tính chỗ chèn (dropTo) + lệch Y (thả nổi). Dời thật khi nhả (onGripUp).
  // Chỗ chèn tính theo trung điểm GỐC (chốt lúc grab) — KHÔNG đọc rect đang bị dịch
  // (rect đang translate → vòng lặp phản hồi, giật).
  const targetFromY = (y: number): number => {
    const mids = midsRef.current;
    for (let k = 0; k < mids.length; k++) {
      if (y < mids[k]) return k;
    }
    return mids.length;
  };
  const onGripDown = (i: number) => (e: any) => {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    dragRef.current = i; dropRef.current = i; startY.current = e.clientY;
    // chốt cao hàng + trung điểm GỐC mọi hàng NGAY (trước khi transform áp vào)
    const rects = rowRefs.current.map((el) => el?.getBoundingClientRect() || null);
    midsRef.current = rects.map((r) => (r ? r.top + r.height / 2 : Infinity));
    setRowH(rects[i]?.height || 0); setDragIdx(i); setDropTo(i); setDy(0);
    navigator.vibrate?.(8);                 // rung nhẹ "nhấc lên" (máy hỗ trợ)
  };
  const onGripMove = (e: any) => {
    if (dragRef.current == null) return;
    const to = targetFromY(e.clientY);
    if (to !== dropRef.current) navigator.vibrate?.(4);   // rung tick mỗi lần khe nhảy
    dropRef.current = to;
    setDy(e.clientY - startY.current);
    setDropTo(to);
  };
  const onGripUp = () => {
    const from = dragRef.current;
    dragRef.current = null;
    if (from == null) return;
    const to = dropRef.current;
    const ins = to > from ? to - 1 : to;                 // vị trí cuối sau khi bỏ chính nó
    navigator.vibrate?.(12);                             // rung "thả xuống"
    // GLIDE: cho dòng đang giữ trượt về đúng khe (transition bật), rồi mới dời list
    // thật khi xong → không giật (nhấc tay là về slot mượt, không nhảy).
    setSettling(true);
    setDy((ins - from) * rowH);
    window.setTimeout(() => {
      setList((l) => {
        const n = l.slice();
        const [it] = n.splice(from, 1);
        n.splice(Math.max(0, Math.min(ins, n.length)), 0, it);
        return n;
      });
      setDragIdx(null); setSettling(false); setDy(0);
    }, 180);
  };

  // Dịch từng hàng: hàng đang giữ theo ngón; hàng giữa khe trượt ±1 hàng để mở chỗ.
  const rowTy = (i: number): number => {
    if (dragIdx == null) return 0;
    if (i === dragIdx) return dy;
    if (dragIdx < dropTo && i > dragIdx && i < dropTo) return -rowH;   // kéo xuống → trượt lên
    if (dropTo < dragIdx && i >= dropTo && i < dragIdx) return rowH;   // kéo lên → trượt xuống
    return 0;
  };

  const apply = () => { onApply(list.map((it) => it.name)); onClose(); };

  return createPortal(
    <div class="sp-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="sp-sheet">
        <div class="sp-title"><Icon name="users" size={16} /> Sắp thứ tự thợ</div>
        <div class="sp-list wo-list">
          {list.length === 0 && <div class="muted small" style="padding:14px 16px">Chưa có thợ nào trong bảng.</div>}
          {list.map((it, i) => (
            <div class={"wo-row" + (dragIdx === i ? " floating" : "") + (dragIdx === i && settling ? " settling" : "")}
              key={it.id}
              ref={(el: any) => { rowRefs.current[i] = el; }}
              style={`transform:translateY(${rowTy(i)}px)` + (dragIdx === i && !settling ? " scale(1.03)" : "")}>
              <span class="wo-grip" title="Kéo để đổi chỗ"
                onPointerDown={onGripDown(i)} onPointerMove={onGripMove}
                onPointerUp={onGripUp} onPointerCancel={onGripUp}>
                <Icon name="menu" size={18} />
              </span>
              <span class="wo-idx">{i + 1}</span>
              <span class="wo-name">{it.name}</span>
              <button class="btn small wo-mv" disabled={i === 0} title="Lên" onClick={() => swap(i, -1)}><Icon name="chevronDown" class="wo-up" size={16} /></button>
              <button class="btn small wo-mv" disabled={i === list.length - 1} title="Xuống" onClick={() => swap(i, 1)}><Icon name="chevronDown" size={16} /></button>
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
