// Chọn 1 giá trị qua POPUP neo ĐỈNH màn hình (danh sách + ô tìm nằm TRÊN, bàn phím
// dưới không che). Thay <select> tĩnh khắp app. Cho autocomplete động dùng PickerPopup.
// Nối: ui/Icon, useScrollLock, format.foldVN. Portal ra body → không bị cắt bởi overflow.
import { useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "./Icon";
import { foldVN } from "../format";

export type SPOption = { value: string | number; label: string; sub?: string };

export function SelectPopup({
  value, options, onChange, placeholder = "Chọn…", searchable, onCreate, disabled, title, class: cls,
}: {
  value?: string | number | null;
  options: SPOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  searchable?: boolean;
  onCreate?: (name: string) => void;   // hiện "➕ Tạo …" khi gõ tên chưa có
  disabled?: boolean;
  title?: string;                       // tiêu đề popup
  class?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  useScrollLock(open);

  const cur = options.find((o) => String(o.value) === String(value ?? ""));
  const nq = foldVN(q.trim());
  const filtered = nq ? options.filter((o) => foldVN(`${o.label} ${o.sub || ""}`).includes(nq)) : options;
  const close = () => { setOpen(false); setQ(""); };
  const pick = (v: string | number) => { onChange(String(v)); close(); };

  return (
    <>
      <button type="button" class={"sp-trigger " + (cls || "")} disabled={disabled} onClick={() => setOpen(true)}>
        <span class={cur ? "" : "muted"}>{cur ? cur.label : placeholder}</span>
        <Icon name="chevronDown" size={16} />
      </button>
      {open && createPortal(
        <div class="sp-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) close(); }}>
          <div class="sp-sheet">
            {title && <div class="sp-title">{title}</div>}
            {(searchable || onCreate) && (
              <input class="sp-search" autofocus placeholder="Tìm…" value={q}
                onInput={(e: any) => setQ(e.target.value)} />
            )}
            <div class="sp-list">
              {filtered.map((o) => (
                <button type="button" key={o.value}
                  class={"sp-opt" + (String(o.value) === String(value ?? "") ? " on" : "")}
                  onClick={() => pick(o.value)}>
                  <span>{o.label}{o.sub && <span class="muted small"> · {o.sub}</span>}</span>
                  {String(o.value) === String(value ?? "") && <Icon name="check" size={16} />}
                </button>
              ))}
              {onCreate && nq && !filtered.some((o) => foldVN(o.label) === nq) && (
                <button type="button" class="sp-opt create" onClick={() => { onCreate(q.trim()); close(); }}>
                  <Icon name="plus" size={15} /> Tạo “{q.trim()}”
                </button>
              )}
              {!filtered.length && !onCreate && <div class="sp-empty muted">Không có mục</div>}
            </div>
            <button type="button" class="sp-close" onClick={close}>Đóng</button>
          </div>
        </div>, document.body)}
    </>
  );
}
