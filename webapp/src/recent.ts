// MỤC GẦN ĐÂY của trang ☰ Thêm — nhớ các mục menu user vừa mở, mới nhất lên đầu.
// Ghi theo hashchange TOÀN CỤC (initRecent gọi ở main.tsx) nên vào từ đâu cũng tính:
// menu, thanh dưới, deep-link từ thông báo. Lưu ở localStorage THEO MÁY (mỗi người
// một điện thoại; không đẩy lên server — đây là thói quen dùng, không phải dữ liệu).
// Nối: homeMenu.findMenuItem (trang đang mở thuộc mục nào), pages/Home.tsx (hiển thị).
import { findMenuItem } from "./homeMenu";

const KEY = "home_recent_v1";
const MAX = 12;   // nhớ dư ra so với 6 ô hiện — lọc theo quyền xong vẫn đủ mục

// Không tính là "mục vừa xem": chính trang menu, và trang đăng nhập/cài đặt (đăng
// xuất rồi vào lại sẽ đẩy nó lên đầu, che mất mục người ta thật sự hay dùng).
const SKIP = new Set(["#/home", "#/login"]);

function read(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function write(list: string[]): void {
  try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))); } catch { /* hết chỗ thì thôi */ }
}

/** Ghi nhận 1 lượt mở trang. Trang không thuộc mục menu nào (vd chi tiết đơn) thì bỏ qua. */
export function recordVisit(rawHash: string): void {
  const hash = (rawHash || "").split("?")[0].trim();
  if (SKIP.has(hash)) return;
  const item = findMenuItem(hash);
  if (!item || SKIP.has(item.href)) return;
  const list = read().filter((h) => h !== item.href);
  list.unshift(item.href);
  write(list);
}

/** Href các mục vừa mở, mới nhất trước (chưa lọc quyền — Home lọc). */
export function recentHrefs(): string[] {
  return read();
}

export function clearRecent(): void {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}

let started = false;
/** Bật theo dõi (gọi 1 lần ở main.tsx). Ghi luôn trang đang mở lúc khởi động. */
export function initRecent(): void {
  if (started) return;
  started = true;
  recordVisit(location.hash);
  window.addEventListener("hashchange", () => recordVisit(location.hash));
}
