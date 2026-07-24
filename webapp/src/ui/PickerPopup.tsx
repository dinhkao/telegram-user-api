// Autocomplete qua POPUP neo ĐỈNH màn hình (ô tìm + kết quả nằm TRÊN, bàn phím dưới
// không che). onSearch(q) trả options (mảng hoặc Promise). Trigger hiện value hiện tại.
// Dùng cho CustomerPicker (async /api/customers) + ProductPicker (lọc catalog).
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "./usePopupBack";
import { Icon } from "./Icon";
import { ErrorState } from "./states";

export type PickOpt = { key: string; label: string; sub?: string };

export function PickerPopup({
  value, placeholder, title, onSearch, onPick, allowFreeText, disabled, class: cls,
}: {
  value?: string;                                   // text hiện trên trigger
  placeholder?: string;
  title?: string;                                   // tiêu đề sheet (như SelectPopup)
  onSearch: (q: string) => PickOpt[] | Promise<PickOpt[]>;
  onPick: (opt: PickOpt) => void;
  allowFreeText?: boolean;                          // cho dùng đúng text đã gõ (mã tự do)
  disabled?: boolean;
  class?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [list, setList] = useState<PickOpt[]>([]);
  const [err, setErr] = useState("");
  const seq = useRef(0);
  const searchRef = useRef<HTMLInputElement>(null);
  useScrollLock(open);
  // Focus ô tìm khi mở (autofocus attr không đáng tin trên portal/WebView)
  useEffect(() => { if (open) requestAnimationFrame(() => searchRef.current?.focus()); }, [open]);

  // Lỗi mạng KHÔNG được đội lốt "Không tìm thấy" (người dùng sẽ tưởng chưa có →
  // tạo trùng). onSearch cứ để reject — hiện ErrorState + Thử lại tại chỗ.
  const run = async (v: string) => {
    const my = ++seq.current;
    let r: PickOpt[];
    try {
      r = await onSearch(v);
    } catch (e: any) {
      if (my === seq.current) setErr(e?.message || "Lỗi tải danh sách");
      return;
    }
    if (my !== seq.current) return;   // phản hồi cũ về muộn → bỏ
    setErr("");
    setList(r);
  };
  useEffect(() => { if (open) run(q); }, [open]);   // mở → chạy tìm với q hiện tại
  const onInput = (v: string) => { setQ(v); run(v); };
  const close = () => { setOpen(false); setQ(""); };
  usePopupBack(open, close);
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
            {title && <div class="sp-title">{title}</div>}
            <input ref={searchRef} class="sp-search" placeholder={placeholder || "Tìm…"} value={q}
              onInput={(e: any) => onInput(e.target.value)} />
            <div class="sp-list">
              {err && <ErrorState msg={err} onRetry={() => run(q)} />}
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
              {!list.length && !err && !allowFreeText && <div class="sp-empty muted">{q.trim() ? "Không tìm thấy" : "Gõ để tìm…"}</div>}
            </div>
            <button type="button" class="sp-close" onClick={close}>Đóng</button>
          </div>
        </div>, document.body)}
    </>
  );
}
