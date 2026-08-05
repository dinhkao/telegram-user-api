// Nhớ KIỂU HIỂN THỊ (Thẻ / Bảng) của 2 trang nhập khoản tiền theo tháng
// (#/nhap-ung, #/nhap-phu-cap) — mỗi trang 1 khoá localStorage riêng, mặc định Thẻ
// (hợp điện thoại; bảng hợp máy tính khi cần đối chiếu/sắp xếp nhiều dòng).
import { useState } from "preact/hooks";

export type EntryView = "card" | "table";

export function useEntryView(key: string): [EntryView, (v: EntryView) => void] {
  const [view, setViewState] = useState<EntryView>(() => {
    try { return localStorage.getItem(key) === "table" ? "table" : "card"; } catch { return "card"; }
  });
  const setView = (v: EntryView) => {
    setViewState(v);
    try { localStorage.setItem(key, v); } catch { /**/ }
  };
  return [view, setView];
}
