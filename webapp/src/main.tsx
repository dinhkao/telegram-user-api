// Entry — hash router (#/orders, #/order/:id, #/create, #/customers, #/login)
// + thanh nav dưới + banner offline/hàng đợi. Connects to: pages/*, api.ts.
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { currentUser, replayQueue } from "./api";
import { getQueue } from "./offline";
import { getStatus, onStatus, startRealtime, stopRealtime, type RealtimeStatus } from "./realtime";
import { CreateOrder } from "./pages/CreateOrder";
import { Customers } from "./pages/Customers";
import { CustomerDetail } from "./pages/CustomerDetail";
import { PriceLists } from "./pages/PriceLists";
import { PriceListDetail } from "./pages/PriceListDetail";
import { Login } from "./pages/Login";
import { OrderDetail } from "./pages/OrderDetail";
import { OrdersList } from "./pages/OrdersList";
import { ProductionList } from "./pages/ProductionList";
import { ProductionDetail } from "./pages/ProductionDetail";
import { InventoryList } from "./pages/InventoryList";
import { InventoryDetail } from "./pages/InventoryDetail";
import { BoxDetail } from "./pages/BoxDetail";
import "./styles.css";

// Nhớ vị trí cuộn theo hash cho các trang KHÔNG tự quản (OrdersList/OrderDetail đã
// tự nhớ). Lưu scrollY của trang rời đi, khôi phục khi quay lại (poll vì nội dung
// tải bất đồng bộ, trang cao dần). Bỏ qua trang #/order* và khi có ?focus (deep-link).
const scrollMem = new Map<string, number>();
const selfManagesScroll = (h: string) => h.startsWith("#/order");

// Lưu scrollY của trang RỜI ĐI ngay tại hashchange (DOM cũ còn nguyên → scrollY
// đúng, chưa bị clamp bởi trang mới). Cài 1 lần trước khi render.
let _lastHash = window.location.hash || "#/orders";
window.addEventListener("hashchange", () => {
  if (!selfManagesScroll(_lastHash)) scrollMem.set(_lastHash, window.scrollY);
  _lastHash = window.location.hash || "#/orders";
});

function useScrollMemory(hash: string, hasFocus: boolean) {
  useEffect(() => {
    if (hasFocus || selfManagesScroll(hash)) return; // focus/tự-quản thắng
    const y = scrollMem.get(hash) ?? 0;
    let tries = 0;
    const iv = setInterval(() => {
      window.scrollTo(0, y);
      if (Math.abs(window.scrollY - y) <= 2 || ++tries > 40) clearInterval(iv);
    }, 25);
    return () => clearInterval(iv);
  }, [hash, hasFocus]);
}

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
  const [menuOpen, setMenuOpen] = useState(false);
  const user = currentUser();
  // Webapp luôn cùng origin với server (APK nạp URL từ xa qua Tailscale) nên không
  // còn màn hình cài server_url — chỉ cần đăng nhập.
  const showLogin = hash === "#/login" || !user;
  const authed = !!user;

  // Chuẩn hoá URL hash về #/login khi cần đăng nhập — làm trong effect,
  // KHÔNG sửa location trong lúc render (gây trắng trang lần đầu, phải reload).
  useEffect(() => {
    if (showLogin && hash !== "#/login") window.location.hash = "#/login";
  }, [showLogin, hash]);

  // Kênh realtime (/ws): bật khi đã đăng nhập, tắt khi đăng xuất.
  useEffect(() => {
    if (authed) startRealtime();
    else stopRealtime();
  }, [authed]);

  let page;
  const orderMatch = hash.match(/^#\/order\/(-?\d+)/);
  const prodMatch = hash.match(/^#\/san_xuat\/(-?\d+)/);
  const khoMatch = hash.match(/^#\/kho\/([^?]+)/);
  const boxMatch = hash.match(/^#\/thung\/(\d+)/);
  const khachMatch = hash.match(/^#\/khach\/([^?]+)/);
  const bangGiaMatch = hash.match(/^#\/bang-gia\/([^?]+)/);
  // Deep-link từ notification: ?focus=comment:123 / ?focus=image:45 → cuộn + nháy
  const focusMatch = hash.match(/[?&]focus=([a-z]+):(\d+)/i);
  const focusEl = focusMatch ? `${focusMatch[1]}-${focusMatch[2]}` : undefined;
  useScrollMemory(hash, !!focusEl);
  if (showLogin) page = <Login />;
  else if (orderMatch) page = <OrderDetail threadId={orderMatch[1]} focus={focusEl} />;
  else if (prodMatch) page = <ProductionDetail threadId={prodMatch[1]} focus={focusEl} />;
  else if (hash.startsWith("#/san_xuat")) page = <ProductionList />;
  else if (boxMatch) page = <BoxDetail boxId={boxMatch[1]} />;
  else if (khoMatch) page = <InventoryDetail code={decodeURIComponent(khoMatch[1])} />;
  else if (hash.startsWith("#/kho")) page = <InventoryList />;
  else if (hash.startsWith("#/create")) page = <CreateOrder />;
  else if (khachMatch) page = <CustomerDetail ckey={decodeURIComponent(khachMatch[1])} />;
  else if (hash.startsWith("#/customers")) page = <Customers />;
  else if (bangGiaMatch) page = <PriceListDetail listId={decodeURIComponent(bangGiaMatch[1])} />;
  else if (hash.startsWith("#/bang-gia")) page = <PriceLists />;
  else page = <OrdersList />;

  const tab = (h: string) => (hash.startsWith(h) ? "tab active" : "tab");
  return (
    <div class="app">
      {!showLogin && (
        <header class="app-bar">
          <span class="app-title">🍬 Đơn hàng</span>
          <div class="app-bar-right">
            <RealtimeDot />
            <button class="btn small" title="Tải lại" onClick={() => window.location.reload()}>🔄 Tải lại</button>
            <a class="btn small" href="#/login" title="Cài đặt">⚙️</a>
          </div>
        </header>
      )}
      <OfflineBanner />
      <main class="page">{page}</main>
      {!showLogin && (
        <nav class="bottom-nav">
          <a class={hash === "#/orders" || orderMatch ? "tab active" : "tab"} href="#/orders">📋 Đơn</a>
          <a class={tab("#/customers")} href="#/customers">👤 Khách</a>
          <a class={tab("#/create")} href="#/create">➕ Tạo</a>
          <a class={tab("#/san_xuat")} href="#/san_xuat">🏭 SX</a>
          <a class={tab("#/kho")} href="#/kho">📦 Kho</a>
          <button class={hash.startsWith("#/bang-gia") ? "tab nav-more active" : "tab nav-more"} onClick={() => setMenuOpen(true)} title="Thêm">☰</button>
        </nav>
      )}
      {menuOpen && !showLogin && (
        <div class="modal-overlay" onClick={() => setMenuOpen(false)}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head">Mục khác</div>
            <a class="menu-item" href="#/bang-gia" onClick={() => setMenuOpen(false)}>💰 Bảng giá chung</a>
            <button class="menu-item" onClick={() => setMenuOpen(false)}>✕ Đóng</button>
          </div>
        </div>
      )}
    </div>
  );
}

render(<App />, document.getElementById("app")!);
