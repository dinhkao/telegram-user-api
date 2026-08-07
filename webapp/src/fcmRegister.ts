/** Đăng ký token FCM của MÁY này theo user đang đăng nhập.
 *
 *  Trước đây push bắn topic chung "orders" nên ai cài app cũng nhận — kể cả vai trò
 *  bó hẹp `chat_luong`. Gửi token lên server (POST /api/fcm/register) thì server
 *  gửi push theo từng máy và lọc được người nhận.
 *
 *  Token lấy từ cầu JS của APK: window.AndroidApp.fcmToken(). Chạy trên trình duyệt
 *  thường (không có cầu) thì không làm gì. Kết nối: api.ts (postJSON/currentUser),
 *  server_app/fcm_routes.py.
 */
import { currentUser, postJSON } from "./api";

const SENT_KEY = "fcm_token_sent";
const RETRY_MS = 6000;
const MAX_RETRY = 2;

let started = false;   // chặn gọi trùng trong 1 phiên (mỗi lần authed đổi vẫn chỉ 1 lần)

function bridgeToken(): string {
  try {
    const fn = (window as any).AndroidApp?.fcmToken;
    return typeof fn === "function" ? String(fn.call((window as any).AndroidApp) || "") : "";
  } catch {
    return "";
  }
}

function attempt(left: number) {
  const token = bridgeToken();
  if (!token) {
    // Native có thể chưa lấy xong token lúc app vừa mở → thử lại vài lần rồi thôi.
    if (left > 0) setTimeout(() => attempt(left - 1), RETRY_MS);
    return;
  }
  try {
    if (localStorage.getItem(SENT_KEY) === token) return;   // đã gửi y hệt lần trước
  } catch { /* localStorage bị chặn → cứ gửi */ }
  postJSON("/api/fcm/register", { token })
    .then(() => { try { localStorage.setItem(SENT_KEY, token); } catch { /* bỏ qua */ } })
    .catch(() => {});
}

export function registerFcmToken() {
  if (started) return;
  // Vai trò chat_luong CŨNG đăng ký (server mở riêng /api/fcm/register cho role này):
  // máy dùng chung từng đăng ký dưới user khác → row token đổi về username bó hẹp
  // → server loại máy đó khỏi push. Không gửi thì máy vẫn nhận push của user cũ.
  if (!currentUser()) return;
  if (typeof (window as any).AndroidApp?.fcmToken !== "function") return;
  started = true;
  attempt(MAX_RETRY);
}
