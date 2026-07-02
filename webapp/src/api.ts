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

/** GET network-first; mất mạng → trả cache (kèm cờ _stale) nếu có. */
export async function getJSON(path: string): Promise<any> {
  const url = serverUrl() + path;
  try {
    const res = await fetch(url, { headers: headers() });
    const data = await parse(res);
    writeCache(path, data);
    return data;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    const cached = readCache(path);
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

/** Gửi lại hàng đợi offline (gọi khi online lại / mở app). */
export function replayQueue(): Promise<number> {
  return flushQueue(async (path, body) => {
    const res = await fetch(serverUrl() + path, { method: "POST", headers: headers(), body: JSON.stringify(body) });
    if (!res.ok && res.status !== 401) throw new Error(`retry ${res.status}`);
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
