// Entry — hash router (#/orders, #/order/:id, #/create, #/customers, #/login)
// + thanh nav dưới + banner offline/hàng đợi. Connects to: pages/*, api.ts.
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { currentUser, replayQueue, serverUrl } from "./api";
import { getQueue } from "./offline";
import { getStatus, onStatus, startRealtime, stopRealtime, type RealtimeStatus } from "./realtime";
import { CreateOrder } from "./pages/CreateOrder";
import { Customers } from "./pages/Customers";
import { Login } from "./pages/Login";
import { OrderDetail } from "./pages/OrderDetail";
import { OrdersList } from "./pages/OrdersList";
import { ProductionList } from "./pages/ProductionList";
import { ProductionDetail } from "./pages/ProductionDetail";
import { DetailSheet } from "./DetailSheet";
import "./styles.css";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash || "#/orders");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/orders");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

function OfflineBanner() {
  const [online, setOnline] = useState(navigator.onLine);
  const [queued, setQueued] = useState(getQueue().length);
  useEffect(() => {
    const sync = async () => {
      setOnline(navigator.onLine);
      if (navigator.onLine) {
        await replayQueue().catch(() => {});
      }
      setQueued(getQueue().length);
    };
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    const timer = setInterval(sync, 30000);
    sync();
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
      clearInterval(timer);
    };
  }, []);
  if (online && !queued) return null;
  return (
    <div class="offline-banner">
      {!online ? "📴 Mất mạng — xem dữ liệu đã lưu" : `⏳ Đang gửi lại ${queued} thao tác chờ…`}
    </div>
  );
}

// Chấm trạng thái realtime — xanh: trực tiếp, vàng nhấp nháy: đang nối lại,
// đỏ: mất kết nối. Ẩn khi đang "online" cho gọn (chỉ hiện khi có vấn đề).
const RT_LABEL: Record<RealtimeStatus, string> = {
  online: "Trực tiếp",
  connecting: "Đang kết nối lại…",
  offline: "Mất kết nối trực tiếp",
};

function RealtimeDot() {
  const [s, setS] = useState<RealtimeStatus>(getStatus());
  useEffect(() => onStatus(setS), []);
  return (
    <div class={`rt-dot rt-${s}`} title={RT_LABEL[s]}>
      <span class="rt-led" />
      {s !== "online" && <span class="rt-text">{RT_LABEL[s]}</span>}
    </div>
  );
}

function App() {
  const hash = useHash();
  const user = currentUser();
  // APK load bundle qua WebViewAssetLoader tại appassets.androidplatform.net —
  // trong đó bắt buộc phải có server_url (fetch relative sẽ trỏ nhầm vào assets)
  const inApk = window.location.hostname === "appassets.androidplatform.net" || window.location.protocol === "file:";
  const needSetup = inApk && !serverUrl();
  const showLogin = hash === "#/login" || !user || needSetup;
  const authed = !!user && !needSetup;

  // Chuẩn hoá URL hash về #/login khi cần đăng nhập/cài server — làm trong effect,
  // KHÔNG sửa location trong lúc render (gây trắng trang lần đầu, phải reload).
  useEffect(() => {
    if (showLogin && hash !== "#/login") window.location.hash = "#/login";
  }, [showLogin, hash]);

  // Kênh realtime (/ws): bật khi đã đăng nhập, tắt khi đăng xuất.
  useEffect(() => {
    if (authed) startRealtime();
    else stopRealtime();
  }, [authed]);

  const orderMatch = hash.match(/^#\/order\/(-?\d+)/);
  const prodMatch = hash.match(/^#\/san_xuat\/(-?\d+)/);
  // Deep-link từ notification: ?focus=comment:123 / ?focus=image:45 → cuộn + nháy
  const focusMatch = hash.match(/[?&]focus=([a-z]+):(\d+)/i);
  const focusEl = focusMatch ? `${focusMatch[1]}-${focusMatch[2]}` : undefined;

  // Trang nền (dashboard) — chi tiết mở đè lên nền tương ứng để giữ nguyên state/
  // cuộn của danh sách phía sau (đơn↔chi tiết đơn, SX↔chi tiết SX).
  let page;
  if (showLogin) page = <Login />;
  else if (orderMatch || hash === "#/orders" || hash === "#/" || hash === "") page = <OrdersList />;
  else if (prodMatch || hash.startsWith("#/san_xuat")) page = <ProductionList />;
  else if (hash.startsWith("#/create")) page = <CreateOrder />;
  else if (hash.startsWith("#/customers")) page = <Customers />;
  else page = <OrdersList />;

  // Lớp chi tiết (bottom-sheet) đè lên nền
  let overlay = null;
  if (!showLogin && orderMatch) overlay = <OrderDetail threadId={orderMatch[1]} focus={focusEl} />;
  else if (!showLogin && prodMatch) overlay = <ProductionDetail threadId={prodMatch[1]} />;
  const closeSheet = () => history.back();

  const tab = (h: string) => (hash.startsWith(h) ? "tab active" : "tab");
  return (
    <div class="app">
      {!showLogin && (
        <header class="app-bar">
          <span class="app-title">🍬 Đơn hàng</span>
          <div class="app-bar-right">
            <RealtimeDot />
            <button class="btn small" title="Tải lại" onClick={() => window.location.reload()}>🔄 Tải lại</button>
          </div>
        </header>
      )}
      <OfflineBanner />
      <main class="page">{page}</main>
      {overlay && (
        <DetailSheet key={hash.split("?")[0]} onClose={closeSheet}>
          {overlay}
        </DetailSheet>
      )}
      {!showLogin && (
        <nav class="bottom-nav">
          <a class={hash === "#/orders" || orderMatch ? "tab active" : "tab"} href="#/orders">📋 Đơn</a>
          <a class={tab("#/create")} href="#/create">➕ Tạo</a>
          <a class={tab("#/san_xuat")} href="#/san_xuat">🏭 SX</a>
          <a class={tab("#/customers")} href="#/customers">👤 Khách</a>
          <a class="tab" href="#/login">⚙️</a>
        </nav>
      )}
    </div>
  );
}

render(<App />, document.getElementById("app")!);
