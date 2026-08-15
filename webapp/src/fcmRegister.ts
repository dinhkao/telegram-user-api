/** Đăng ký token FCM của MÁY này theo user đang đăng nhập.
 *
 *  Trước đây push bắn topic chung "orders" nên ai cài app cũng nhận — kể cả vai trò
 *  bó hẹp `chat_luong`. Gửi token lên server (POST /api/fcm/register) thì server
 *  gửi push theo từng máy và lọc được người nhận.
 *
 *  ⚠ Token FCM XOAY (Firebase tự đổi định kỳ / cài lại app). APK giữ WebView sống
 *  nhiều ngày (foreground service) nên nếu chỉ đăng ký lúc khởi động, máy có thể
 *  chạy hàng tuần với token cũ ⇒ server bắn vào token chết, FCM vẫn trả "ok" mà
 *  máy KHÔNG hiện gì. Vì vậy kiểm tra lại MỖI LẦN app quay ra tiền cảnh (resume)
 *  và gửi lại khi token khác lần trước.
 *
 *  Token lấy từ cầu JS của APK: window.AndroidApp.fcmToken(). Chạy trên trình duyệt
 *  thường (không có cầu) thì không làm gì. Kết nối: api.ts (postJSON/currentUser),
 *  server_app/fcm_routes.py.
 */
import { currentUser, postJSON } from "./api";

const SENT_KEY = "fcm_token_sent";
const RETRY_MS = 6000;
const MAX_RETRY = 2;
const RECHECK_MS = 60_000;   // resume liên tục thì không gọi cầu JS quá dày

let started = false;   // chặn gắn listener trùng trong 1 phiên
let lastCheck = 0;

function bridgeToken(): string {
  try {
    const fn = (window as any).AndroidApp?.fcmToken;
    return typeof fn === "function" ? String(fn.call((window as any).AndroidApp) || "") : "";
  } catch {
    return "";
  }
}

function attempt(left: number, force = false) {
  const token = bridgeToken();
  if (!token) {
    // Native có thể chưa lấy xong token lúc app vừa mở → thử lại vài lần rồi thôi.
    if (left > 0) setTimeout(() => attempt(left - 1, force), RETRY_MS);
    return;
  }
  // Lúc KHỞI ĐỘNG luôn gửi (force): 1 POST bé xíu, đổi lại `updated_at` cho biết máy
  // nào còn sống và tự sửa mọi trường hợp row trên server lệch/mất. Chỉ lần kiểm lại
  // khi resume mới bỏ qua nếu token y hệt (resume xảy ra liên tục).
  if (!force) {
    try {
      if (localStorage.getItem(SENT_KEY) === token) return;
    } catch { /* localStorage bị chặn → cứ gửi */ }
  }
  postJSON("/api/fcm/register", { token })
    .then(() => { try { localStorage.setItem(SENT_KEY, token); } catch { /* bỏ qua */ } })
    .catch(() => {});
}

/** Kiểm tra lại khi app quay ra tiền cảnh — token xoay giữa chừng vẫn tới được server. */
function recheck() {
  if (document.visibilityState !== "visible" || !currentUser()) return;
  const now = Date.now();
  if (now - lastCheck < RECHECK_MS) return;
  lastCheck = now;
  attempt(MAX_RETRY);
}

export function registerFcmToken() {
  if (started) return;
  // Vai trò chat_luong CŨNG đăng ký (server mở riêng /api/fcm/register cho role này):
  // máy dùng chung từng đăng ký dưới user khác → row token đổi về username bó hẹp
  // → server loại máy đó khỏi push. Không gửi thì máy vẫn nhận push của user cũ.
  if (!currentUser()) return;
  if (typeof (window as any).AndroidApp?.fcmToken !== "function") return;
  started = true;
  lastCheck = Date.now();
  attempt(MAX_RETRY, true);
  document.addEventListener("visibilitychange", recheck);
  window.addEventListener("focus", recheck);
}
