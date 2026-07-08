// SEARCH BAR CHUẨN toàn app (kiểu dashboard Đơn) — input search + nút ✕ xoá.
// Mọi trang list dùng CÁI NÀY, đừng tự chế <input> riêng. Tìm không dấu do
// server (vn_normalize) hoặc caller lo (foldVN) — component chỉ lo UI.
// Kèm FilterActiveBar: panel "Đang lọc: … · n · ✕ Bỏ lọc" chuẩn (vàng, viền trái).
import { Icon } from "./Icon";

export function SearchBar({ value, onInput, placeholder = "Tìm…", autofocus }: {
  value: string;
  onInput: (v: string) => void;
  placeholder?: string;
  autofocus?: boolean;
}) {
  return (
    <div class="sbar">
      <Icon name="search" size={15} class="sbar-ic" />
      <input class="sbar-in" type="search" placeholder={placeholder} value={value}
        autofocus={autofocus} onInput={(e: any) => onInput(e.target.value)} />
      {value ? (
        <button class="sbar-x" onClick={() => onInput("")} aria-label="Xoá tìm kiếm">
          <Icon name="close" size={14} />
        </button>
      ) : null}
    </div>
  );
}

/** Panel "Đang lọc" chuẩn — hiện khi có filter/search khác mặc định.
 *  parts: các mảnh mô tả (bỏ qua phần rỗng). count: số kết quả (tuỳ chọn). */
export function FilterActiveBar({ parts, count, onClear }: {
  parts: (string | null | undefined | false)[];
  count?: number | null;
  onClear: () => void;
}) {
  const shown = parts.filter(Boolean) as string[];
  if (!shown.length) return null;
  return (
    <div class="filter-active-bar">
      <span class="fab-txt">
        <Icon name="search" size={14} /> Đang lọc: <b>{shown.join(" · ")}</b>
        {count != null ? <span class="fab-count"> · {count} kết quả</span> : null}
      </span>
      <button class="fab-clear" onClick={onClear}>✕ Bỏ lọc</button>
    </div>
  );
}
