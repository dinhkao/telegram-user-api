// Ô tìm + chọn mã sản phẩm (autocomplete lọc tại chỗ trên catalog đã tải).
// Dùng ở ProductionDetail (đổi SP phiếu) và ProductionList (tạo phiếu). Lọc theo
// MÃ SP (code). Mở dạng POPUP neo đỉnh (PickerPopup) — bàn phím không che list.
import type { ProdCatalogItem } from "../api";
import { PickerPopup } from "../ui/PickerPopup";

export function ProductPicker({ catalog, value, onPick, placeholder }: {
  catalog: ProdCatalogItem[];
  value: string;
  onPick: (code: string) => void;
  placeholder?: string;
}) {
  return (
    <PickerPopup
      value={value}
      title="Chọn mã SP"
      placeholder={placeholder || "Tìm mã SP"}
      onSearch={(q) => {
        const n = q.trim().toLowerCase();
        return (n ? catalog.filter((c) => c.code.toLowerCase().includes(n)) : catalog)
          .slice(0, 40)
          .map((c) => ({ key: c.code, label: c.code, sub: c.mam != null ? `mâm ${c.mam}` : undefined }));
      }}
      onPick={(o) => onPick(o.key)}
    />
  );
}
