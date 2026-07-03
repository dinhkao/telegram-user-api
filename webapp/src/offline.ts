// Offline: cache GET vào localStorage + hàng đợi POST (chỉ thao tác an toàn khi
// replay: đánh dấu task, bình luận). Sửa đơn/thanh toán KHÔNG queue — RMW blob
// replay trễ dễ mất update. Dùng bởi api.ts.

const CACHE_PREFIX = "cache:";
const QUEUE_KEY = "post_queue";
const CACHE_MAX_AGE_MS = 3 * 24 * 3600 * 1000; // 3 ngày

export function writeCache(path: string, data: any) {
  try {
    localStorage.setItem(CACHE_PREFIX + path, JSON.stringify({ t: Date.now(), data }));
  } catch {
    pruneCache(); // đầy quota → dọn cũ, bỏ qua nếu vẫn lỗi
  }
}

export function readCache(path: string): { t: number; data: any } | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + path);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Date.now() - parsed.t > CACHE_MAX_AGE_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function pruneCache() {
  const keys: { k: string; t: number }[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i)!;
    if (!k.startsWith(CACHE_PREFIX)) continue;
    try {
      keys.push({ k, t: JSON.parse(localStorage.getItem(k)!).t || 0 });
    } catch {
      localStorage.removeItem(k);
    }
  }
  keys.sort((a, b) => a.t - b.t);
  for (const { k } of keys.slice(0, Math.ceil(keys.length / 2))) localStorage.removeItem(k);
}

type QueuedPost = { path: string; body: any; at: number };

export function queuePost(path: string, body: any) {
  const q = getQueue();
  q.push({ path, body, at: Date.now() });
  localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
}

export function getQueue(): QueuedPost[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  } catch {
    return [];
  }
}

/** Gửi lần lượt. Callback trả "ok" (đã gửi) | "drop" (bỏ hẳn) | "keep" (giữ thử sau);
 *  ném exception (mất mạng) = "keep". Trả số item đã gửi. */
export async function flushQueue(send: (path: string, body: any) => Promise<"ok" | "drop" | "keep">): Promise<number> {
  const q = getQueue();
  if (!q.length) return 0;
  const remaining: QueuedPost[] = [];
  let sent = 0;
  for (const item of q) {
    let verdict: "ok" | "drop" | "keep";
    try {
      verdict = await send(item.path, item.body);
    } catch {
      verdict = "keep";
    }
    if (verdict === "ok") sent++;
    else if (verdict === "keep") remaining.push(item);
  }
  // Item được queuePost thêm TRONG lúc flush nằm ở cuối queue hiện tại (sau snapshot q)
  // → giữ lại, đừng ghi đè mất.
  const added = getQueue().slice(q.length);
  localStorage.setItem(QUEUE_KEY, JSON.stringify([...remaining, ...added]));
  return sent;
}
