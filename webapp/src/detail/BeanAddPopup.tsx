// POPUP THÊM cho kho đậu — dùng chung cho "thêm KHO" (Kho A/B…) và "thêm LOẠI ĐẬU"
// (tên + đơn vị chính). Mở từ #/kho-dau/thiet-lap. Nối: api.createBeanPlace/createBean.
import { useState } from "preact/hooks";
import { createBean, createBeanPlace } from "../api";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";

export type BeanAddMode = "place" | "bean";

export function BeanAddPopup({ mode, onClose, onDone }: {
  mode: BeanAddMode;
  onClose: () => void;
  onDone: () => Promise<any> | void;
}) {
  const isPlace = mode === "place";
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("kg");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const submit = async () => {
    const n = name.trim();
    if (!n) return toast(isPlace ? "Nhập tên kho" : "Nhập tên loại đậu", "info");
    setBusy(true);
    try {
      if (isPlace) await createBeanPlace(n, note.trim());
      else await createBean(n, unit.trim() || "kg", note.trim());
      await onDone();
      toast(isPlace ? "Đã thêm kho" : "Đã thêm loại đậu", "ok");
      onClose();
    } catch (e: any) {
      toast(e?.message || "Lỗi", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet bean-add-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head">
          <span><Icon name={isPlace ? "box" : "plus"} size={16} /> {isPlace ? "Thêm kho" : "Thêm loại đậu"}</span>
          <button class="link-btn" title="Đóng" onClick={onClose}><Icon name="close" size={18} /></button>
        </div>

        <div class="bean-form-row">
          <label class="bean-lbl">Tên</label>
          <input class="bean-in" autofocus value={name}
            placeholder={isPlace ? "vd Kho A" : "vd Đậu xanh"}
            onInput={(e: any) => setName(e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") submit(); }} />
        </div>
        {!isPlace && (
          <div class="bean-form-row">
            <label class="bean-lbl">Đơn vị</label>
            <input class="bean-in" value={unit} placeholder="kg"
              onInput={(e: any) => setUnit(e.target.value)}
              onKeyDown={(e: any) => { if (e.key === "Enter") submit(); }} />
          </div>
        )}
        <div class="bean-form-row">
          <label class="bean-lbl">Ghi chú</label>
          <input class="bean-in" value={note} placeholder="Tuỳ chọn"
            onInput={(e: any) => setNote(e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") submit(); }} />
        </div>
        {!isPlace && (
          <p class="muted small">
            Đơn vị chính là thước đo mọi số tồn kho. Đơn vị khác (bao, thùng…) khai
            thêm sau ở nút ⇄ của loại đậu.
          </p>
        )}

        <div class="row">
          <button class="btn" onClick={onClose}>Huỷ</button>
          <button class="btn primary" disabled={busy || !name.trim()} onClick={submit}>
            {busy ? "Đang lưu…" : isPlace ? "Thêm kho" : "Thêm loại đậu"}
          </button>
        </div>
      </div>
    </div>
  );
}
