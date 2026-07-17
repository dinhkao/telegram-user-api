// Segmented "Ô thùng | Gọn" DÙNG CHUNG cho các trang kho (KhoBoxes / InventoryDetail /
// PlaceDetail) — trước đây copy 3 nơi (2 chip + inline style flex-end). Kiểu xem được
// NHỚ theo storageKey khi rời trang (module scope, giống hành vi memBoxView/memInvView/
// memView cũ — không persist qua reload). Dùng:
//   const [view, setView] = useBoxView("kho_boxes", "compact");
//   <BoxViewToggle value={view} onChange={setView} end />
import { useState } from "preact/hooks";

export type BoxView = "grid" | "compact";

// Nhớ kiểu xem theo trang (storageKey) khi rời trang — thay các biến module lẻ cũ.
const mem = new Map<string, BoxView>();

export function useBoxView(storageKey: string, def: BoxView): [BoxView, (v: BoxView) => void] {
  const [view, setView] = useState<BoxView>(mem.get(storageKey) ?? def);
  const set = (v: BoxView) => { mem.set(storageKey, v); setView(v); };
  return [view, set];
}

// `end` = tự bọc 1 hàng căn phải (dùng khi toggle đứng riêng 1 dòng trên lưới thùng).
export function BoxViewToggle({ value, onChange, end }: {
  value: BoxView; onChange: (v: BoxView) => void; end?: boolean;
}) {
  const chips = (
    <span class="box-view-toggle">
      <button class={"chip" + (value === "grid" ? " active" : "")} onClick={() => onChange("grid")}>Ô thùng</button>
      <button class={"chip" + (value === "compact" ? " active" : "")} onClick={() => onChange("compact")}>Gọn</button>
    </span>
  );
  return end ? <div class="box-view-row">{chips}</div> : chips;
}
