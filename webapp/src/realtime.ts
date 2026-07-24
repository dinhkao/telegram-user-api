// Kênh realtime tới server qua /ws — nhận event "đơn đổi" / "danh sách đổi" rồi
// phát cho subscriber. Tự kết nối lại (backoff luỹ thừa). Mất rồi nối lại → phát
// "resync" để subscriber tải lại (phòng đã lỡ event lúc rớt). Chỉ nhận, không gửi.
// Dùng bởi: main.tsx (bật/tắt theo đăng nhập), OrdersList, OrderDetail.
import { getToken, serverUrl } from "./api";

export type RealtimeEvent =
  | { type: "order_changed"; thread_id: string; row: any | null }
  | { type: "orders_changed" }
  | { type: "production_changed"; thread_id: string; row: any | null }
  | { type: "productions_changed" }
  | { type: "customer_changed"; key: string | null }
  | { type: "inventory_changed" }
  | { type: "box_changed"; box_id: string | null }
  | { type: "price_lists_changed" }
  | { type: "quy_changed" }
  | { type: "tasks_changed" }
  | { type: "workers_changed" }
  | { type: "report_slips_changed" }
  | { type: "return_changed"; id: string }
  | { type: "purchase_changed"; id: string }
  | { type: "supplier_changed"; id: string | null }
  | { type: "disposal_changed"; id: string }
  | { type: "area_changed"; id: string }
  | { type: "cashbox_changed" }
  | { type: "banner_changed" }
  | { type: "notif_added"; notif: any }
  | { type: "report_lock"; thread_id: string | null; holder: string | null }
  | { type: "stocktake_lock"; stocktake_id: string | null; holder: string | null }
  | { type: "report_draft"; thread_id: string | null; draft: any }
  | { type: "stock_pick_lock"; thread_id: string | null; code: string; holder: string | null }
  | { type: "invoice_edit_lock"; thread_id: string | null; holder: string | null }
  | { type: "invoice_creating"; thread_id: string | null; holder: string | null }
  | { type: "app_reload" }
  | { type: "resync" };

// Các event server phát (không kèm "resync" — đó là do client tự sinh khi nối lại).
const _SERVER_EVENTS = new Set([
  "order_changed", "orders_changed", "production_changed", "productions_changed",
  "customer_changed", "inventory_changed", "box_changed", "price_lists_changed",
  "quy_changed", "notif_added", "report_lock", "report_draft", "banner_changed",
  "tasks_changed", "workers_changed", "report_slips_changed", "return_changed", "stock_pick_lock", "invoice_edit_lock",
  "invoice_creating",
  "purchase_changed", "supplier_changed", "disposal_changed", "stocktake_lock",
  "cashbox_changed", "app_reload", "area_changed",
]);

type Handler = (e: RealtimeEvent) => void;

/** Event có LIÊN QUAN tới thực thể của 1 base ("/api/order/123", "/api/media/box/5"…)?
 *  Dùng cho Comments/Images/History để chỉ tải lại khi ĐÚNG thực thể đổi. resync = luôn. */
export function eventMatchesBase(base: string, e: RealtimeEvent): boolean {
  if (e.type === "resync") return true;
  if ((e.type === "order_changed" || e.type === "production_changed") && e.thread_id) return base.endsWith("/" + e.thread_id);
  if (e.type === "box_changed" && e.box_id) return base.endsWith("/" + e.box_id);
  // Lịch sử VỊ TRÍ kho: mọi biến động kho (nhập/xuất/chuyển/xoá) → inventory_changed
  // (không mang id) → tải lại lịch sử của trang vị trí đang mở.
  if (e.type === "inventory_changed" && base.includes("/place/")) return true;
  if (e.type === "return_changed" && e.id) return base.includes("/return/") && base.endsWith("/" + e.id);
  if (e.type === "purchase_changed" && e.id) return base.includes("/purchase/") && base.endsWith("/" + e.id);
  if (e.type === "supplier_changed" && e.id) return base.includes("/supplier/") && base.endsWith("/" + e.id);
  if (e.type === "disposal_changed" && e.id) return base.includes("/disposal/") && base.endsWith("/" + e.id);
  return false;
}

export type RealtimeStatus = "online" | "connecting" | "offline";
type StatusHandler = (s: RealtimeStatus) => void;

const handlers = new Set<Handler>();
const statusHandlers = new Set<StatusHandler>();
let status: RealtimeStatus = "offline";
let ws: WebSocket | null = null;
let backoff = 1000;
let stopped = false;
let everConnected = false;
// Chống socket "nửa sống": WebView bị suspend (tắt màn hình/đổi mạng) làm TCP đứt
// KHÔNG có FIN → ws vẫn báo OPEN, onclose không bao giờ bắn, client tưởng online mà
// không nhận gì nữa. Ping protocol-level của aiohttp JS không thấy được, nên server
// phát thêm {"type":"ping"} app-level mỗi 25s (server_app/websocket_routes.py) và
// client watchdog tự đóng khi im lặng quá lâu (chỉ bật sau khi ĐÃ thấy ping đầu —
// server cũ chưa có ping thì hành vi y như trước, không tự đóng nhầm socket khoẻ).
let lastMsgAt = 0;
let sawPing = false;
let hiddenAt = 0;
let watchdog: any = null;
let listenersInstalled = false;
const PING_STALE_MS = 65_000;   // > 2 chu kỳ ping 25s + dư
const HIDDEN_FORCE_MS = 30_000; // ẩn quá lâu → nghi socket chết, nối lại cho chắc

function setStatus(s: RealtimeStatus) {
  if (s === status) return;
  status = s;
  statusHandlers.forEach((h) => {
    try {
      h(s);
    } catch {
      /* subscriber lỗi không làm chết vòng phát */
    }
  });
}

export function getStatus(): RealtimeStatus {
  return status;
}

/** Đăng ký nhận trạng thái kết nối; gọi ngay 1 lần với trạng thái hiện tại. */
export function onStatus(h: StatusHandler): () => void {
  statusHandlers.add(h);
  h(status);
  return () => {
    statusHandlers.delete(h);
  };
}

function wsUrl(): string {
  // Web: same-origin. APK/WebView: serverUrl() là IP Tailscale đã cấu hình.
  const base = serverUrl() || location.origin;
  // ?token= để server xác thực /ws khi bật WEB_AUTH (browser không set header được)
  const t = getToken();
  return base.replace(/^http/, "ws") + "/ws" + (t ? `?token=${encodeURIComponent(t)}` : "");
}

function emit(e: RealtimeEvent) {
  handlers.forEach((h) => {
    try {
      h(e);
    } catch {
      /* subscriber lỗi không được làm chết vòng phát */
    }
  });
}

function schedule() {
  if (stopped) return;
  setTimeout(connect, backoff);
  backoff = Math.min(backoff * 2, 15000);
}

function connect() {
  if (stopped || ws) return;
  setStatus("connecting");
  try {
    ws = new WebSocket(wsUrl());
  } catch {
    setStatus("offline");
    schedule();
    return;
  }
  ws.onopen = () => {
    backoff = 1000;
    lastMsgAt = Date.now();
    setStatus("online");
    if (everConnected) emit({ type: "resync" }); // lần nối LẠI mới cần tải bù
    everConnected = true;
  };
  ws.onmessage = (ev) => {
    lastMsgAt = Date.now();
    let data: any;
    try {
      data = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (data?.type === "ping") { sawPing = true; return; } // keepalive — không phát cho subscriber
    // ÉP tải lại: admin bấm "Buộc mọi máy tải lại" → server broadcast → reload ngay.
    if (data?.type === "app_reload") { try { window.location.reload(); } catch { /* ignore */ } return; }
    if (data && _SERVER_EVENTS.has(data.type)) emit(data);
  };
  const self = ws;
  ws.onclose = () => {
    if (ws !== self) return; // close muộn của socket cũ → đừng null socket hiện tại
    ws = null;
    setStatus(stopped ? "offline" : "connecting");
    schedule();
  };
  ws.onerror = () => {
    try {
      ws?.close();
    } catch {
      /* onclose sẽ lo việc nối lại */
    }
  };
}

/** Ép nối lại NGAY (bỏ backoff): đóng socket hiện tại nếu có; onclose sẽ schedule
 *  connect sau 1s. Socket đã chết ngầm thì close() vô hại — chỉ để kích chu trình. */
function kick() {
  if (stopped) return;
  backoff = 1000;
  if (ws) {
    try { ws.close(); } catch { /* onclose lo phần còn lại */ }
  } else {
    connect(); // đang giữa 2 lần retry → nối luôn khỏi chờ hết backoff
  }
}

function checkStale() {
  // Chỉ hoạt động khi server ĐÃ chứng minh có phát ping (sawPing) — server bản cũ
  // không ping thì watchdog im lặng, không tự đóng socket khoẻ mạnh.
  if (stopped || !ws || !sawPing) return;
  if (Date.now() - lastMsgAt > PING_STALE_MS) kick();
}

function installLifecycleListeners() {
  if (listenersInstalled || typeof document === "undefined") return;
  listenersInstalled = true;
  // App resume: WebView suspend làm socket chết không FIN → onclose không bắn.
  // Ẩn đủ lâu rồi hiện lại → chủ động nối lại (phát resync → các trang tải bù).
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      hiddenAt = Date.now();
      return;
    }
    const hiddenFor = hiddenAt ? Date.now() - hiddenAt : 0;
    hiddenAt = 0;
    if (stopped) return;
    if (!ws || hiddenFor > HIDDEN_FORCE_MS) kick();
    else checkStale();
  });
  // Mạng quay lại (đổi WiFi↔4G) → nối ngay, khỏi chờ backoff.
  window.addEventListener("online", () => kick());
}

export function startRealtime() {
  stopped = false;
  installLifecycleListeners();
  if (!watchdog) watchdog = setInterval(checkStale, 15_000);
  connect();
}

export function stopRealtime() {
  stopped = true;
  everConnected = false; // đăng xuất→đăng nhập lại: lần nối đầu KHÔNG phát resync thừa
  if (watchdog) { clearInterval(watchdog); watchdog = null; }
  try {
    ws?.close();
  } catch {
    /* ignore */
  }
  ws = null;
  setStatus("offline");
}

/** Đăng ký nhận event; trả hàm huỷ đăng ký. */
export function onRealtime(h: Handler): () => void {
  handlers.add(h);
  return () => {
    handlers.delete(h);
  };
}
