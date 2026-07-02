// Kênh realtime tới server qua /ws — nhận event "đơn đổi" / "danh sách đổi" rồi
// phát cho subscriber. Tự kết nối lại (backoff luỹ thừa). Mất rồi nối lại → phát
// "resync" để subscriber tải lại (phòng đã lỡ event lúc rớt). Chỉ nhận, không gửi.
// Dùng bởi: main.tsx (bật/tắt theo đăng nhập), OrdersList, OrderDetail.
import { getToken, serverUrl } from "./api";

export type RealtimeEvent =
  | { type: "order_changed"; thread_id: string; row: any | null }
  | { type: "orders_changed" }
  | { type: "resync" };

type Handler = (e: RealtimeEvent) => void;

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
    if (data && (data.type === "order_changed" || data.type === "orders_changed")) emit(data);
  };
  ws.onclose = () => {
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
