// Autocomplete qua POPUP neo ĐỈNH màn hình (ô tìm + kết quả nằm TRÊN, bàn phím dưới
// không che). onSearch(q) trả options (mảng hoặc Promise). Trigger hiện value hiện tại.
// Dùng cho CustomerPicker (async /api/customers) + ProductPicker (lọc catalog).
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "./Icon";

export type PickOpt = { key: string; label: string; sub?: string };

export function PickerPopup({
  value, placeholder, onSearch, onPick, allowFreeText, disabled, class: cls,
}: {
  value?: string;                                   // text hiện trên trigger
  placeholder?: string;
  onSearch: (q: string) => PickOpt[] | Promise<PickOpt[]>;
  onPick: (opt: PickOpt) => void;
  allowFreeText?: boolean;                          // cho dùng đúng text đã gõ (mã tự do)
  disabled?: boolean;
  class?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [list, setList] = useState<PickOpt[]>([]);
  const seq = useRef(0);
  useScrollLock(open);

  const run = async (v: string) => {
    const my = ++seq.current;
    const r = await onSearch(v);
    if (my !== seq.current) return;   // phản hồi cũ về muộn → bỏ
    setList(r);
  };
  useEffect(() => { if (open) run(q); }, [open]);   // mở → chạy tìm với q hiện tại
  const onInput = (v: string) => { setQ(v); run(v); };
  const close = () => { setOpen(false); setQ(""); };
  const pick = (o: PickOpt) => { onPick(o); close(); };

  return (
    <>
      <button type="button" class={"sp-trigger " + (cls || "")} disabled={disabled} onClick={() => setOpen(true)}>
        <span class={value ? "" : "muted"}>{value || placeholder || "Chọn…"}</span>
        <Icon name="search" size={15} />
      </button>
      {open && createPortal(
        <div class="sp-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) close(); }}>
          <div class="sp-sheet">
            <input class="sp-search" autofocus placeholder={placeholder || "Tìm…"} value={q}
              onInput={(e: any) => onInput(e.target.value)} />
            <div class="sp-list">
              {allowFreeText && q.trim() && !list.some((o) => o.key === q.trim()) && (
                <button type="button" class="sp-opt create" onClick={() => pick({ key: q.trim(), label: q.trim() })}>
                  <Icon name="check" size={15} /> Dùng “{q.trim()}”
                </button>
              )}
              {list.map((o) => (
                <button type="button" key={o.key} class="sp-opt" onClick={() => pick(o)}>
                  <span><b>{o.label}</b>{o.sub && <span class="muted small"> · {o.sub}</span>}</span>
                </button>
              ))}
              {!list.length && !allowFreeText && <div class="sp-empty muted">{q.trim() ? "Không tìm thấy" : "Gõ để tìm…"}</div>}
            </div>
            <button type="button" class="sp-close" onClick={close}>Đóng</button>
          </div>
        </div>, document.body)}
    </>
  );
}
