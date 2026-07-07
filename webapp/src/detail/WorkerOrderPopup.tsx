// Popup CHỌN + SẮP THỨ TỰ thợ cho bảng báo cáo — mở từ nút ⚙️ ở trang sửa báo cáo.
// Hiện MỌI thợ (danh sách chung ∪ thợ đang trong bảng). Tick chọn thợ nào DÙNG trong
// bảng; KÉO grip ≡ (cảm ứng+chuột) hoặc ↑↓ để sắp thứ tự. "Áp dụng" → trả danh sách
// thợ ĐÃ CHỌN đúng thứ tự cho trang (dựng lại bảng, giữ số liệu thợ cũ) + lưu bền
// sort_order thợ toàn cục.
// Kéo mượt kiểu iOS: dòng đang giữ theo ngón tức thì + phóng nhẹ; các dòng khác TRƯỢT
// mở khe (transition CSS); nhả tay GLIDE về chỗ rồi mới dời list thật (khỏi giật/lag).
// Neo đỉnh (sp-overlay/sp-sheet), usePopupBack + useScrollLock như mọi popup.
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";

export type WorkerEntry = { name: string; on: boolean };
type Item = { id: number; name: string; on: boolean };
const toItems = (es: WorkerEntry[]): Item[] => es.map((e, id) => ({ id, name: e.name, on: e.on }));

export function WorkerOrderPopup({
  open, entries, onClose, onApply,
}: {
  open: boolean;
  entries: WorkerEntry[];          // MỌI thợ (chung ∪ bảng); on = đang dùng trong bảng
  onClose: () => void;
  onApply: (selected: string[]) => void;   // thợ đã chọn, đúng thứ tự
}) {
  const [list, setList] = useState<Item[]>(() => toItems(entries));
  // trạng thái kéo (dùng ref để pointermove khỏi phụ thuộc closure cũ)
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dropTo, setDropTo] = useState<number>(0);
  const [dy, setDy] = useState(0);
  const [rowH, setRowH] = useState(0);
  const [settling, setSettling] = useState(false);
  const dragRef = useRef<number | null>(null);
  const dropRef = useRef<number>(0);
  const midsRef = useRef<number[]>([]);
  const startY = useRef(0);
  const rowRefs = useRef<(HTMLElement | null)[]>([]);
  useScrollLock(open);
  usePopupBack(open, onClose);
  // Seed CHỈ lúc mở (open false→true) — KHÔNG mỗi render (entries là mảng mới mỗi lần).
  useEffect(() => { if (open) setList(toItems(entries)); }, [open]);   // eslint-disable-line
  if (!open) return null;

  const toggle = (i: number) => setList((l) => l.map((x, k) => (k === i ? { ...x, on: !x.on } : x)));
  const swap = (i: number, d: -1 | 1) => setList((l) => {
    const j = i + d;
    if (j < 0 || j >= l.length) return l;
    const n = l.slice();
    [n[i], n[j]] = [n[j], n[i]];
    return n;
  });

  // ── Kéo: chỗ chèn theo trung điểm GỐC (chốt lúc grab) — không đọc rect đang dịch.
  const targetFromY = (y: number): number => {
    const mids = midsRef.current;
    for (let k = 0; k < mids.length; k++) if (y < mids[k]) return k;
    return mids.length;
  };
  const onGripDown = (i: number) => (e: any) => {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    dragRef.current = i; dropRef.current = i; startY.current = e.clientY;
    const rects = rowRefs.current.map((el) => el?.getBoundingClientRect() || null);
    midsRef.current = rects.map((r) => (r ? r.top + r.height / 2 : Infinity));
    setRowH(rects[i]?.height || 0); setDragIdx(i); setDropTo(i); setDy(0);
    navigator.vibrate?.(8);
  };
  const onGripMove = (e: any) => {
    if (dragRef.current == null) return;
    const to = targetFromY(e.clientY);
    if (to !== dropRef.current) navigator.vibrate?.(4);
    dropRef.current = to;
    setDy(e.clientY - startY.current);
    setDropTo(to);
  };
  const onGripUp = () => {
    const from = dragRef.current;
    dragRef.current = null;
    if (from == null) return;
    const to = dropRef.current;
    const ins = to > from ? to - 1 : to;
    navigator.vibrate?.(12);
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
    if (dragIdx < dropTo && i > dragIdx && i < dropTo) return -rowH;
    if (dropTo < dragIdx && i >= dropTo && i < dragIdx) return rowH;
    return 0;
  };

  const chosen = list.filter((it) => it.on).length;
  const apply = () => { onApply(list.filter((it) => it.on).map((it) => it.name)); onClose(); };

  return createPortal(
    <div class="sp-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="sp-sheet">
        <div class="sp-title"><Icon name="users" size={16} /> Chọn &amp; sắp thứ tự thợ</div>
        <div class="muted small wo-hint">Tick thợ dùng trong bảng · kéo <Icon name="menu" size={13} /> để sắp thứ tự</div>
        <div class="sp-list wo-list">
          {list.length === 0 && <div class="muted small" style="padding:14px 16px">Chưa có thợ nào.</div>}
          {list.map((it, i) => (
            <div class={"wo-row" + (it.on ? "" : " off") + (dragIdx === i ? " floating" : "") + (dragIdx === i && settling ? " settling" : "")}
              key={it.id}
              ref={(el: any) => { rowRefs.current[i] = el; }}
              style={`transform:translateY(${rowTy(i)}px)` + (dragIdx === i && !settling ? " scale(1.03)" : "")}>
              <button class={"wo-check" + (it.on ? " on" : "")} title={it.on ? "Bỏ khỏi bảng" : "Dùng trong bảng"} onClick={() => toggle(i)}>
                {it.on && <Icon name="check" size={15} />}
              </button>
              <span class="wo-name" onClick={() => toggle(i)}>{it.name}</span>
              <button class="btn small wo-mv" disabled={i === 0} title="Lên" onClick={() => swap(i, -1)}><Icon name="chevronDown" class="wo-up" size={16} /></button>
              <button class="btn small wo-mv" disabled={i === list.length - 1} title="Xuống" onClick={() => swap(i, 1)}><Icon name="chevronDown" size={16} /></button>
              <span class="wo-grip" title="Kéo để đổi chỗ"
                onPointerDown={onGripDown(i)} onPointerMove={onGripMove}
                onPointerUp={onGripUp} onPointerCancel={onGripUp}>
                <Icon name="menu" size={18} />
              </span>
            </div>
          ))}
        </div>
        <div class="wo-foot">
          <span class="muted small wo-count">{chosen} thợ</span>
          <button class="btn" onClick={onClose}>Đóng</button>
          <button class="btn primary" disabled={chosen === 0} onClick={apply}><Icon name="check" size={16} /> Áp dụng</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
