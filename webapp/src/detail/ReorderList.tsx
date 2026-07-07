// Danh sách KÉO-THẢ sắp thứ tự + tick chọn dùng chung — popup chọn/sắp thợ (báo cáo)
// VÀ trang quản lý thợ (#/tho) đều xài, để cảm giác kéo mượt kiểu iOS chỉ sửa 1 chỗ.
// Sở hữu thứ tự + trạng thái tick nội bộ (seed lại khi `seedSig` đổi); báo ra ngoài qua
// onReorder(ids) / onToggle(id,next) / onDelete(id). Kéo grip ≡ (pointer-events: cảm
// ứng+chuột) hoặc ↑↓; dòng đang giữ theo ngón tức thì + phóng nhẹ + haptic, dòng khác
// TRƯỢT mở khe (transition CSS), nhả tay GLIDE về chỗ rồi commit (tắt transition 1 frame
// khỏi re-animate). Không remount dòng đang giữ (key theo id). CSS: .wo-* trong styles.css.
import { useEffect, useRef, useState } from "preact/hooks";
import { Icon } from "../ui/Icon";

export type RItem = { id: number | string; name: string; on: boolean };

export function ReorderList({
  items, seedSig, onReorder, onToggle, onDelete, checkKind = "check", trailing,
}: {
  items: RItem[];
  seedSig: string | number;                                   // đổi → seed lại từ items
  onReorder: (ids: (number | string)[]) => void;              // sau khi thả / bấm ↑↓
  onToggle?: (id: number | string, next: boolean) => void;    // tick / bỏ tick
  onDelete?: (id: number | string) => void;                   // nút xoá (ẩn nếu không truyền)
  checkKind?: "check" | "star";
  trailing?: (it: RItem) => any;                              // phần thêm cuối hàng (vd link ›)
}) {
  const [list, setList] = useState<RItem[]>(items);
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dropTo, setDropTo] = useState(0);
  const [dy, setDy] = useState(0);
  const [rowH, setRowH] = useState(0);
  const [settling, setSettling] = useState(false);
  const [noFx, setNoFx] = useState(false);
  const dragRef = useRef<number | null>(null);
  const dropRef = useRef(0);
  const midsRef = useRef<number[]>([]);
  const startY = useRef(0);
  const rowRefs = useRef<(HTMLElement | null)[]>([]);
  // Seed CHỈ khi seedSig đổi (không mỗi render — items là mảng mới mỗi lần cha render).
  useEffect(() => { setList(items); }, [seedSig]);   // eslint-disable-line

  const ids = (l: RItem[]) => l.map((x) => x.id);
  const toggle = (i: number) => setList((l) => {
    const n = l.map((x, k) => (k === i ? { ...x, on: !x.on } : x));
    onToggle?.(n[i].id, n[i].on);
    return n;
  });
  const swap = (i: number, d: -1 | 1) => setList((l) => {
    const j = i + d;
    if (j < 0 || j >= l.length) return l;
    const n = l.slice();
    [n[i], n[j]] = [n[j], n[i]];
    onReorder(ids(n));
    return n;
  });
  const del = (i: number) => setList((l) => {
    const it = l[i];
    onDelete?.(it.id);
    return l.filter((_, k) => k !== i);
  });

  // Chỗ chèn theo trung điểm GỐC (chốt lúc grab) — không đọc rect đang dịch (khỏi giật).
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
      setNoFx(true);
      setList((l) => {
        const n = l.slice();
        const [it] = n.splice(from, 1);
        n.splice(Math.max(0, Math.min(ins, n.length)), 0, it);
        onReorder(ids(n));
        return n;
      });
      setDragIdx(null); setSettling(false); setDy(0);
      requestAnimationFrame(() => requestAnimationFrame(() => setNoFx(false)));
    }, 180);
  };

  const rowTy = (i: number): number => {
    if (dragIdx == null) return 0;
    if (i === dragIdx) return dy;
    if (dragIdx < dropTo && i > dragIdx && i < dropTo) return -rowH;
    if (dropTo < dragIdx && i >= dropTo && i < dragIdx) return rowH;
    return 0;
  };

  return (
    <div class="wo-list">
      {list.map((it, i) => (
        <div class={"wo-row" + (it.on ? "" : " off") + (noFx ? " wo-nofx" : "") + (dragIdx === i ? " floating" : "") + (dragIdx === i && settling ? " settling" : "")}
          key={it.id}
          ref={(el: any) => { rowRefs.current[i] = el; }}
          style={`transform:translateY(${rowTy(i)}px)` + (dragIdx === i && !settling ? " scale(1.03)" : "")}>
          <button class={"wo-check" + (checkKind === "star" ? " star" : "") + (it.on ? " on" : "")}
            title={it.on ? "Bỏ chọn" : "Chọn"} onClick={() => toggle(i)}>
            {(checkKind === "star" || it.on) && <Icon name={checkKind === "star" ? "star" : "check"} size={15} />}
          </button>
          <span class="wo-name" onClick={() => toggle(i)}>{it.name}</span>
          {trailing?.(it)}
          <button class="btn small wo-mv" disabled={i === 0} title="Lên" onClick={() => swap(i, -1)}><Icon name="chevronDown" class="wo-up" size={16} /></button>
          <button class="btn small wo-mv" disabled={i === list.length - 1} title="Xuống" onClick={() => swap(i, 1)}><Icon name="chevronDown" size={16} /></button>
          {onDelete && <button class="btn small wo-del" title="Xoá" onClick={() => del(i)}><Icon name="trash" size={15} /></button>}
          <span class="wo-grip" title="Kéo để đổi chỗ"
            onPointerDown={onGripDown(i)} onPointerMove={onGripMove}
            onPointerUp={onGripUp} onPointerCancel={onGripUp}>
            <Icon name="menu" size={18} />
          </span>
        </div>
      ))}
    </div>
  );
}
