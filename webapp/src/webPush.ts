/** WEB PUSH cho iPhone (PWA "Thêm vào màn hình chính", iOS ≥ 16.4) và trình duyệt không có
 *  APK. Android APK đã có FCM (fcmRegister.ts) → ở trong APK thì bỏ qua hoàn toàn.
 *
 *  ⚠ iPhone: CHỈ app mở từ MÀN HÌNH CHÍNH mới có PushManager (Safari thường thì không) và
 *  Notification.requestPermission() PHẢI gọi ngay trong cú bấm (không await gì trước nó).
 *  Service worker: /app/sw.js (webapp/public). Server: /api/webpush/* (server_app/webpush_routes).
 */
import { currentUser, getJSON, postJSON } from "./api";

export type WebPushState = "apk" | "need-install" | "unsupported" | "denied" | "off" | "on";

export const inApk = () => typeof (window as any).AndroidApp !== "undefined";
export const isIOS = () =>
  /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
export const isStandalone = () =>
  (navigator as any).standalone === true || window.matchMedia?.("(display-mode: standalone)").matches;
const supported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

function b64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  await navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" });
  return navigator.serviceWorker.ready;
}

/** Trạng thái để UI chọn hiển thị gì. */
export async function webPushState(): Promise<WebPushState> {
  if (inApk()) return "apk";
  if (!supported()) return isIOS() && !isStandalone() ? "need-install" : "unsupported";
  if (Notification.permission === "denied") return "denied";
  if (Notification.permission !== "granted") return "off";
  try {
    const reg = await navigator.serviceWorker.getRegistration("/app/");
    return (await reg?.pushManager.getSubscription()) ? "on" : "off";
  } catch { return "off"; }
}

/** Đăng ký (hoặc lấy đăng ký sẵn có) + gửi lên server theo user đang đăng nhập. Khoá server
 *  đổi → huỷ đăng ký cũ, đăng ký lại bằng khoá mới. */
async function subscribeAndSend(): Promise<void> {
  const { enabled, key } = await getJSON("/api/webpush/key", { cache: false });
  if (!enabled || !key) throw new Error("Máy chủ chưa bật thông báo web");
  const reg = await registration();
  const want = b64ToBytes(key);
  let sub = await reg.pushManager.getSubscription();
  const cur = sub?.options?.applicationServerKey ? new Uint8Array(sub.options.applicationServerKey) : null;
  if (sub && cur && (cur.length !== want.length || cur.some((b, i) => b !== want[i]))) {
    await sub.unsubscribe();
    sub = null;
  }
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: want });
  await postJSON("/api/webpush/subscribe", { subscription: sub.toJSON() });
}

/** Gọi TRONG cú bấm nút "Bật thông báo". */
export async function enableWebPush(): Promise<void> {
  if (!supported()) throw new Error(isIOS() ? "Mở app từ MÀN HÌNH CHÍNH rồi bật lại" : "Trình duyệt không hỗ trợ thông báo");
  const perm = await Notification.requestPermission();   // ⚠ phải là lệnh await ĐẦU TIÊN
  if (perm !== "granted") throw new Error("Chưa cho phép thông báo");
  await subscribeAndSend();
}

export async function sendTestWebPush(): Promise<string> {
  const r = await postJSON("/api/webpush/test", {});
  if (!r.ok) throw new Error(r.error || "Gửi thử lỗi");
  return "Đã gửi — xem thông báo trên máy này";
}

/** Mỗi lần mở app (đã đăng nhập): quyền đã cấp → gửi lại đăng ký (gắn đúng user hiện tại,
 *  tự sửa khi server mất row / đổi khoá). Không hỏi quyền ở đây. */
export function syncWebPush(): void {
  if (inApk() || !supported() || !currentUser() || Notification.permission !== "granted") return;
  subscribeAndSend().catch(() => { /* lần sau thử lại */ });
}

/** Bấm thông báo khi app đang mở → service worker nhắn {type:'open', url} → đổi trang. */
export function listenWebPushOpen(): void {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.addEventListener("message", (e: MessageEvent) => {
    const d = e.data || {};
    if (d.type !== "open" || !d.url) return;
    try {
      const h = new URL(d.url, location.origin).hash;
      if (h) location.hash = h;
    } catch { /* bỏ qua */ }
  });
}
