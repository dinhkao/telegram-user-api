// Ô tìm + chọn mã sản phẩm (autocomplete lọc tại chỗ trên catalog đã tải).
// Dùng ở ProductionDetail (đổi SP phiếu) và ProductionList (tạo phiếu). Lọc theo
// MÃ SP (code) — gõ để lọc, bấm để chọn. Dùng chung CSS .ac/.ac-list.
import { useState } from "preact/hooks";
import type { ProdCatalogItem } from "../api";

export function ProductPicker({ catalog, value, onPick, placeholder }: {
  catalog: ProdCatalogItem[];
  value: string;
  onPick: (code: string) => void;
  placeholder?: string;
}) {
  const [q, setQ] = useState(value || "");
  const [open, setOpen] = useState(false);
  // Lọc theo mã (code), không phân biệt hoa/thường. Query rỗng → hiện tất cả.
  const needle = q.trim().toLowerCase();
  const list = (needle ? catalog.filter((c) => c.code.toLowerCase().includes(needle)) : catalog).slice(0, 40);
  const pick = (c: ProdCatalogItem) => { setQ(c.code); setOpen(false); onPick(c.code); };
  return (
    <div class="ac">
      <input
        value={q}
        placeholder={placeholder || "Tìm mã SP"}
        onInput={(e: any) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && list.length > 0 && (
        <ul class="ac-list">
          {list.map((c) => (
            <li key={c.code} onMouseDown={() => pick(c)}>
              <b>{c.code}</b>{c.mam != null ? ` · mâm ${c.mam}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
