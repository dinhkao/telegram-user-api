// Cache + tải dữ liệu dashboard Kho (#/kho) — module scope nên SỐNG QUA UNMOUNT:
// quay lại trang vẽ NGAY từ cache (không spinner toàn trang), chỉ refresh nền khi
// kho có thay đổi. Subscriber realtime cấp-module LUÔN sống: trang Kho đang đóng mà
// kho đổi → đánh dấu dirty, lần mở sau vẽ cache tức thì + refresh nền đúng 1 lượt.
// Nối: ../api (listPlaces/allBoxes/inventoryList), ../realtime.
import { listPlaces, allBoxes, inventoryList, type Place, type KhoBox, type InvProductSummary } from "../api";
import { onRealtime } from "../realtime";

export type KhoData = { places: Place[]; boxes: KhoBox[]; prodSum: InvProductSummary[] };

let cache: KhoData | null = null;
let dirty = false;
let seq = 0;   // chống race: lượt tải cũ về SAU không được ghi đè lượt mới

// Event kho quan tâm — component mở dùng để debounce-refresh, module dùng đánh dirty.
export const KHO_EVENTS = new Set(["resync", "box_changed", "inventory_changed", "production_changed"]);

export function khoCache(): { data: KhoData | null; dirty: boolean } {
  return { data: cache, dirty };
}

/** Tải cả 3 dataset song song. Trả data nếu đây là lượt MỚI NHẤT; trả null nếu đã
 *  có lượt mới hơn khởi động sau (caller bỏ qua — chống dữ liệu "quay ngược").
 *  Lỗi ném ra cho caller quyết (cold → ErrorState, refresh nền → giữ cache im lặng). */
export async function khoLoad(): Promise<KhoData | null> {
  const my = ++seq;
  const [places, boxes, prodSum] = await Promise.all([listPlaces(), allBoxes(), inventoryList()]);
  if (my !== seq) return null;
  cache = { places, boxes, prodSum };
  dirty = false;
  return cache;
}

// LUÔN sống (kể cả khi trang Kho unmount) → không bỏ lỡ thay đổi lúc trang đóng.
// Lúc component đang mở nó tự refresh (debounce) và khoLoad() thành công xoá dirty.
onRealtime((e) => {
  if (KHO_EVENTS.has(e.type)) dirty = true;
});
