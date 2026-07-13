// Đo mức dùng tính năng: TỰ bắt mọi cú bấm nút/link (listener toàn cục, không phải
// sửa từng nút) + lượt xem trang (hashchange), gộp đếm trong RAM rồi gửi 1 batch
// mỗi 20s qua POST /api/usage/batch (mất mạng → offline queue của api.ts).
// Route chuẩn hoá (#/order/123 → #/order/:id); nhãn nút thay số bằng # để không
// nở cardinality. Admin xem tổng hợp ở #/usage. Server: usage_store.
import { postJSON } from "./api";

type Ev = { kind: "view" | "tap"; page: string; label: string; n: number };

const FLUSH_MS = 20_000;
const MAX_KEYS = 400; // trần buffer 1 chu kỳ — chống nhãn động nở vô hạn
const buf = new Map<string, Ev>();
let started = false;

/** '#/order/494175?focus=x' → '#/order/:id' — giữ segment chữ thường tĩnh (lich,
 * hoa-don…), mọi segment động (id, mã SP, tên) thành ':id'. */
export const normalizeHash = (raw: string): string => {
  const segs = (raw || "#/").split("?")[0].replace(/^#\/?/, "").split("/").filter(Boolean);
  if (!segs.length) return "#/";
  const out = [segs[0]];
  for (const seg of segs.slice(1)) out.push(/^[a-z-]+$/.test(seg) ? seg : ":id");
  return "#/" + out.join("/");
};

// Nhãn = 4 TỪ ĐẦU, số → #: nhãn động kiểu "Lọc đơn của <tên khách>" gộp về
// "Lọc đơn của" — vừa không ghi tên khách vào stats vừa không nở cardinality
// (mỗi khách 1 dòng DB thì bảng xếp hạng thành vô nghĩa).
const cleanLabel = (s: string) =>
  s.replace(/\s+/g, " ").replace(/\d[\d.,:%/]*/g, "#").trim()
    .split(" ").slice(0, 4).join(" ").slice(0, 40);

const bump = (kind: Ev["kind"], page: string, label = "") => {
  const key = `${kind}|${page}|${label}`;
  const cur = buf.get(key);
  if (cur) cur.n += 1;
  else if (buf.size < MAX_KEYS) buf.set(key, { kind, page, label, n: 1 });
};

const flush = () => {
  if (!buf.size) return;
  const events = [...buf.values()];
  buf.clear();
  // queueable: mất mạng thì vào offline queue, có mạng gửi lại — không mất đếm.
  postJSON("/api/usage/batch", { events }, { queueable: true }).catch(() => {
    // Gửi lỗi (server lỗi / localStorage đầy không queue được) → trả đếm lại
    // buffer, chu kỳ sau thử tiếp thay vì mất im lặng.
    for (const event of events) {
      const key = `${event.kind}|${event.page}|${event.label}`;
      const cur = buf.get(key);
      if (cur) cur.n += event.n;
      else if (buf.size < MAX_KEYS) buf.set(key, event);
    }
  });
};

const labelFor = (el: HTMLElement): string => {
  // Link điều hướng: nhãn = đích chuẩn hoá (text của link thường là dữ liệu động
  // như tên khách/đơn — vừa nở cardinality vừa không nói lên "tính năng").
  const href = el.tagName === "A" ? el.getAttribute("href") : null;
  if (href && href.startsWith("#")) return "→ " + normalizeHash(href);
  return cleanLabel(
    el.getAttribute("title") || el.getAttribute("aria-label") || el.textContent || "",
  ) || "." + (String((el as any).className || "").split(" ")[0] || "?");
};

export function initUsage() {
  if (started) return;
  started = true;
  bump("view", normalizeHash(location.hash));
  window.addEventListener("hashchange", () => bump("view", normalizeHash(location.hash)));
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    const el = target?.closest?.("button, a, [role=button]") as HTMLElement | null;
    if (el) bump("tap", normalizeHash(location.hash), labelFor(el));
  }, { capture: true, passive: true });
  window.setInterval(flush, FLUSH_MS);
  document.addEventListener("visibilitychange", () => { if (document.hidden) flush(); });
}
