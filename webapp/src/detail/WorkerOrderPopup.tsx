// Popup CHỌN + SẮP THỨ TỰ thợ cho bảng báo cáo — mở từ nút ⚙️ ở trang sửa báo cáo.
// Hiện MỌI thợ (danh sách chung ∪ thợ đang trong bảng). Tick chọn thợ DÙNG trong bảng;
// kéo/↑↓ sắp thứ tự (cơ chế kéo dùng chung ReorderList). "Áp dụng" → trả thợ ĐÃ CHỌN
// đúng thứ tự cho trang. Neo đỉnh (sp-overlay/sp-sheet), usePopupBack + useScrollLock.
import { useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";
import { ReorderList, type RItem } from "./ReorderList";

export type WorkerEntry = { name: string; on: boolean };

export function WorkerOrderPopup({
  open, entries, onClose, onApply,
}: {
  open: boolean;
  entries: WorkerEntry[];          // MỌI thợ (chung ∪ bảng); on = đang dùng trong bảng
  onClose: () => void;
  onApply: (selected: string[]) => void;   // thợ đã chọn, đúng thứ tự
}) {
  const [sel, setSel] = useState<RItem[]>([]);
  const openedRef = useRef(false);
  useScrollLock(open);
  usePopupBack(open, onClose);
  // Seed lúc mở (open false→true) — set state khi render (guard 1 lần) để ReorderList
  // mount với dữ liệu tươi ngay (khỏi lệ thuộc thứ tự effect cha/con).
  if (open && !openedRef.current) { openedRef.current = true; setSel(entries.map((e, i) => ({ id: i, name: e.name, on: e.on }))); }
  if (!open && openedRef.current) openedRef.current = false;
  if (!open) return null;

  const reorder = (order: (number | string)[]) =>
    setSel((l) => order.map((id) => l.find((x) => x.id === id)).filter(Boolean) as RItem[]);
  const toggle = (id: number | string, next: boolean) =>
    setSel((l) => l.map((x) => (x.id === id ? { ...x, on: next } : x)));

  const chosen = sel.filter((x) => x.on).length;
  const apply = () => { onApply(sel.filter((x) => x.on).map((x) => x.name)); onClose(); };

  return createPortal(
    <div class="sp-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="sp-sheet">
        <div class="sp-title"><Icon name="users" size={16} /> Chọn &amp; sắp thứ tự thợ</div>
        <div class="muted small wo-hint">Tick thợ dùng trong bảng · kéo <Icon name="menu" size={13} /> để sắp thứ tự</div>
        <div class="sp-list">
          {sel.length === 0
            ? <div class="muted small" style="padding:14px 16px">Chưa có thợ nào.</div>
            : <ReorderList items={sel} seedSig={0} onReorder={reorder} onToggle={toggle} />}
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
