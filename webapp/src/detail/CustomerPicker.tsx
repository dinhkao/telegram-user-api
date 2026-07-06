// Ô tìm + chọn khách hàng (autocomplete /api/customers). Dùng ở CreateOrder
// (tạo đơn) và OrderDetail (gán khách cho đơn chưa có). Gọi onPick khi chọn.
// Mở dạng POPUP neo đỉnh (PickerPopup) — bàn phím không che kết quả.
import { useState } from "preact/hooks";
import { getJSON } from "../api";
import { money } from "../format";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";

export function CustomerPicker({ onPick, placeholder }: {
  onPick: (c: { key: string; name: string } | null) => void;
  placeholder?: string;
}) {
  const [picked, setPicked] = useState("");
  const search = async (v: string): Promise<PickOpt[]> => {
    if (!v.trim()) return [];
    const d = await getJSON(`/api/customers?search=${encodeURIComponent(v)}&limit=10`, { cache: false })
      .catch(() => ({ customers: [] }));
    return (d.customers || []).map((c: any) => ({
      key: c.key, label: c.name, sub: c.debt ? `nợ ${money(c.debt)}đ` : undefined,
    }));
  };
  return (
    <PickerPopup
      value={picked}
      placeholder={placeholder || "Tìm khách hàng"}
      onSearch={search}
      onPick={(o) => { setPicked(o.label); onPick({ key: o.key, name: o.label }); }}
    />
  );
}
