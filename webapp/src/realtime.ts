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
  | { type: "return_changed"; id: string }
  | { type: "banner_changed" }
  | { type: "notif_added"; notif: any }
  | { type: "report_lock"; thread_id: string | null; holder: string | null }
  | { type: "report_draft"; thread_id: string | null; draft: any }
  | { type: "resync" };

// Các event server phát (không kèm "resync" — đó là do client tự sinh khi nối lại).
const _SERVER_EVENTS = new Set([
  "order_changed", "orders_changed", "production_changed", "productions_changed",
  "customer_changed", "inventory_changed", "box_changed", "price_lists_changed",
  "quy_changed", "notif_added", "report_lock", "report_draft", "banner_changed",
  "tasks_changed", "workers_changed", "return_changed",
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
    setStatus("online");
    if (everConnected) emit({ type: "resync" }); // lần nối LẠI mới cần tải bù
    everConnected = true;
  };
  ws.onmessage = (ev) => {
    let data: any;
    try {
      data = JSON.parse(ev.data);
    } catch {
      return;
    }
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

export function startRealtime() {
  stopped = false;
  connect();
}

export function stopRealtime() {
  stopped = true;
  everConnected = false; // đăng xuất→đăng nhập lại: lần nối đầu KHÔNG phát resync thừa
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
