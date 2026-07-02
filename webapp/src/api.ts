// Lớp gọi API — gắn token, base URL cấu hình được (WebView trỏ Tailscale IP),
// cache GET (network-first, rớt mạng đọc cache) + hàng đợi POST offline (offline.ts).
import { flushQueue, queuePost, readCache, writeCache } from "./offline";

export function serverUrl(): string {
  // Trong APK (file:// hoặc appassets) bắt buộc có server_url; trên web dùng same-origin.
  return localStorage.getItem("server_url") || "";
}

export function setServerUrl(url: string) {
  localStorage.setItem("server_url", url.replace(/\/+$/, ""));
}

export function getToken(): string {
  return localStorage.getItem("token") || "";
}

export function setAuth(token: string, user: { username: string; display_name: string; role: string } | null) {
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
  if (user) localStorage.setItem("user", JSON.stringify(user));
  else localStorage.removeItem("user");
}

export function currentUser(): { username: string; display_name: string; role: string } | null {
  try {
    return JSON.parse(localStorage.getItem("user") || "null");
  } catch {
    return null;
  }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const t = getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parse(res: Response): Promise<any> {
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    window.location.hash = "#/login";
    throw new ApiError(401, data.error || "Cần đăng nhập");
  }
  if (!res.ok) throw new ApiError(res.status, data.error || `Lỗi ${res.status}`);
  return data;
}

/** GET network-first; mất mạng → trả cache (kèm cờ _stale) nếu có.
 *  cache=false cho kết quả search theo phím gõ — không rác localStorage. */
export async function getJSON(path: string, opts?: { cache?: boolean }): Promise<any> {
  const url = serverUrl() + path;
  const useCache = opts?.cache !== false;
  try {
    const res = await fetch(url, { headers: headers() });
    const data = await parse(res);
    if (useCache) writeCache(path, data);
    return data;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    const cached = useCache ? readCache(path) : null;
    if (cached) return { ...cached.data, _stale: true, _cachedAt: cached.t };
    throw new Error("Mất mạng và chưa có dữ liệu lưu sẵn");
  }
}

/** POST; queueable=true → mất mạng thì xếp hàng đợi, có mạng gửi lại. */
export async function postJSON(path: string, body: any, opts?: { queueable?: boolean }): Promise<any> {
  const url = serverUrl() + path;
  try {
    const res = await fetch(url, { method: "POST", headers: headers(), body: JSON.stringify(body) });
    return await parse(res);
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (opts?.queueable) {
      queuePost(path, body);
      return { ok: true, _queued: true };
    }
    throw new Error("Mất mạng — thao tác này cần mạng, thử lại sau");
  }
}

/** Gửi lại hàng đợi offline (gọi khi online lại / mở app).
 *  401 → GIỮ item (token hết hạn, đăng nhập lại sẽ gửi tiếp — không mất dữ liệu);
 *  4xx khác → BỎ (đơn không còn / dữ liệu sai, retry mãi vô ích); lỗi mạng/5xx → giữ. */
export function replayQueue(): Promise<number> {
  return flushQueue(async (path, body) => {
    const res = await fetch(serverUrl() + path, { method: "POST", headers: headers(), body: JSON.stringify(body) });
    if (res.ok) return "ok";
    if (res.status === 401) return "keep";
    if (res.status >= 400 && res.status < 500) return "drop";
    return "keep";
  });
}

export async function login(username: string, pin: string): Promise<any> {
  const res = await fetch(serverUrl() + "/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, pin }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Đăng nhập thất bại");
  setAuth(data.token, data.user);
  return data.user;
}

// ── Helpers cho trình nhập hoá đơn nâng cao ──────────────────────────────

/** Autocomplete mã/tên SP. Không cache (kết quả theo phím gõ). */
export async function searchProducts(q: string): Promise<{ code: string; name: string }[]> {
  const d = await getJSON(`/api/products?search=${encodeURIComponent(q)}&limit=15`, { cache: false });
  return d.products || [];
}

export type PriceInfo = { price: number; source: "personal" | "shared" | null; list_name: string | null };

/** Giá SP theo khách + bảng giá nào (price 0 nếu không có). */
export async function fetchCustomerPrice(customerId: string, product: string): Promise<PriceInfo> {
  if (!customerId || !product) return { price: 0, source: null, list_name: null };
  const d = await postJSON("/api/customer/price", { customer_id: customerId, product });
  return { price: d.price || 0, source: d.source || null, list_name: d.list_name || null };
}

/** Tạo hoá đơn KiotViet cho đơn (tương đương lệnh 'tạo hd'). */
export async function createKiotVietInvoice(threadId: string | number): Promise<any> {
  return postJSON("/api/order/invoice/create-kiotviet", { thread_id: Number(threadId) });
}

/** URL HTML hoá đơn để mở tab mới (kèm token cho WebView/khi bật auth). */
export function invoiceHtmlUrl(threadId: string | number): string {
  const t = getToken();
  return `${serverUrl()}/api/order/${Number(threadId)}/invoice-html${t ? `?token=${encodeURIComponent(t)}` : ""}`;
}
