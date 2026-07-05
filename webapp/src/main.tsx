// Entry — hash router (#/orders, #/order/:id, #/create, #/customers, #/login)
// + thanh nav dưới + banner offline/hàng đợi. Connects to: pages/*, api.ts.
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { currentUser, replayQueue, netOk, onNetStatus } from "./api";
import { getQueue } from "./offline";
import { getStatus, onStatus, startRealtime, stopRealtime, type RealtimeStatus } from "./realtime";
import { CreateOrder } from "./pages/CreateOrder";
import { Customers } from "./pages/Customers";
import { CustomerDetail } from "./pages/CustomerDetail";
import { PriceLists } from "./pages/PriceLists";
import { PriceListDetail } from "./pages/PriceListDetail";
import { Login } from "./pages/Login";
import { FeedbackHost } from "./ui/feedback";
import { OrderDetail } from "./pages/OrderDetail";
import { OrdersList, resetOrdersScroll } from "./pages/OrdersList";
import { DeliveryCalendar } from "./pages/DeliveryCalendar";
import { ActivityLog } from "./pages/ActivityLog";
import { ProductionList } from "./pages/ProductionList";
import { ProductionDetail } from "./pages/ProductionDetail";
import { ProductionReportEdit } from "./pages/ProductionReportEdit";
import { InventoryList } from "./pages/InventoryList";
import { InventoryDetail } from "./pages/InventoryDetail";
import { BoxDetail } from "./pages/BoxDetail";
import "./styles.css";

// Nhớ vị trí cuộn theo hash cho các trang KHÔNG tự quản (OrdersList/OrderDetail đã
// tự nhớ). Lưu scrollY của trang rời đi, khôi phục khi quay lại (poll vì nội dung
// tải bất đồng bộ, trang cao dần). Bỏ qua trang #/order* và khi có ?focus (deep-link).
// ── Khôi phục vị trí cuộn CHUYÊN NGHIỆP — 1 hệ trung tâm cho MỌI trang:
//  • BACK (nút back trình duyệt / BackLink history.back() → popstate) → về ĐÚNG vị trí cũ.
//  • FORWARD (bấm link, mở chi tiết mới) → lên ĐẦU trang.
// Khôi phục chịu nội dung tải trễ (theo dõi chiều cao, lặp tới khi tới nơi + cao ổn định)
// và TỰ HUỶ khi người dùng chạm/cuộn. Key = hash sạch (bỏ ?focus/query).
if (typeof history !== "undefined" && "scrollRestoration" in history) history.scrollRestoration = "manual";

const scrollMem = new Map<string, number>();
const _SCROLL_MAX = 60;
const cleanHash = (h: string) => (h || "#/orders").split("?")[0];
function rememberScroll(h: string) {
  scrollMem.set(cleanHash(h), window.scrollY);
  if (scrollMem.size > _SCROLL_MAX) {
    const k = scrollMem.keys().next().value; // FIFO evict cũ nhất
    if (k !== undefined) scrollMem.delete(k);
  }
}

let _lastHash = cleanHash(window.location.hash);
let _navBack = false; // điều hướng vừa rồi là back? → hook quyết định khôi phục hay lên đầu
let _pop = false;
window.addEventListener("popstate", () => { _pop = true; });
window.addEventListener("hashchange", () => {
  rememberScroll(_lastHash);            // lưu vị trí trang RỜI ĐI (DOM cũ còn → scrollY đúng)
  _navBack = _pop; _pop = false;
  _lastHash = cleanHash(window.location.hash);
});

function useScrollMemory(hash: string, hasFocus: boolean) {
  useEffect(() => {
    if (hasFocus) return;                              // deep-link (?focus) tự cuộn tới phần tử
    if (!_navBack) { window.scrollTo(0, 0); return; }  // FORWARD → lên đầu
    const target = scrollMem.get(cleanHash(hash)) ?? 0; // BACK → khôi phục
    if (target <= 4) { window.scrollTo(0, 0); return; }
    let cancelled = false, raf = 0, lastH = -1, stableAt = 0;
    const start = performance.now();
    const onUser = () => { cancelled = true; };
    const evs: (keyof WindowEventMap)[] = ["wheel", "touchstart", "keydown", "pointerdown"];
    evs.forEach((ev) => window.addEventListener(ev, onUser, { passive: true }));
    const cleanup = () => { cancelAnimationFrame(raf); evs.forEach((ev) => window.removeEventListener(ev, onUser)); };
    const step = () => {
      if (cancelled) return cleanup();
      window.scrollTo(0, target);
      const now = performance.now();
      const h = document.documentElement.scrollHeight;
      if (h !== lastH) { lastH = h; stableAt = now; }  // trang còn cao lên (nội dung tải trễ)
      const reached = Math.abs(window.scrollY - target) <= 2;
      if ((reached && now - stableAt > 400) || now - start > 6000) return cleanup();
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return cleanup;
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
  // "online" = có TỚI ĐƯỢC server (theo fetch thực), KHÔNG theo navigator.onLine (WebView
  // qua Tailscale báo sai → banner "mất mạng" ảo dù mạng vẫn chạy).
  const [online, setOnline] = useState(netOk());
  const [queued, setQueued] = useState(getQueue().length);
  useEffect(() => {
    const offNet = onNetStatus((ok) => {
      setOnline(ok);
      if (ok) replayQueue().then(() => setQueued(getQueue().length)).catch(() => {});
    });
    const sync = async () => {
      if (navigator.onLine) await replayQueue().catch(() => {});
      setQueued(getQueue().length);
    };
    window.addEventListener("online", sync);
    const timer = setInterval(sync, 30000);
    sync();
    return () => {
      offNet();
      window.removeEventListener("online", sync);
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
  const prodEditMatch = hash.match(/^#\/san_xuat\/(-?\d+)\/bao-cao/);
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
  else if (prodEditMatch) page = <ProductionReportEdit threadId={prodEditMatch[1]} />;
  else if (prodMatch) page = <ProductionDetail threadId={prodMatch[1]} focus={focusEl} />;
  else if (hash.startsWith("#/san_xuat")) page = <ProductionList />;
  else if (boxMatch) page = <BoxDetail boxId={boxMatch[1]} />;
  else if (khoMatch) page = <InventoryDetail code={decodeURIComponent(khoMatch[1])} />;
  else if (hash.startsWith("#/kho")) page = <InventoryList />;
  else if (hash.startsWith("#/lich-su")) page = <ActivityLog />;
  else if (hash.startsWith("#/lich")) page = <DeliveryCalendar />;
  else if (hash.startsWith("#/create")) page = <CreateOrder />;
  else if (khachMatch) page = <CustomerDetail ckey={decodeURIComponent(khachMatch[1])} />;
  else if (hash.startsWith("#/customers")) page = <Customers />;
  else if (bangGiaMatch) page = <PriceListDetail listId={decodeURIComponent(bangGiaMatch[1])} />;
  else if (hash.startsWith("#/bang-gia")) page = <PriceLists />;
  else page = <OrdersList />;

  const tab = (h: string) => (hash.startsWith(h) ? "tab active" : "tab");
  return (
    <div class="app">
      <FeedbackHost />
      {!showLogin && (
        <header class="app-bar">
          <span class="app-title">🍬 Đơn hàng</span>
          <div class="app-bar-right">
            <RealtimeDot />
            <button class="icon-btn" title="Tải lại" onClick={() => window.location.reload()}>🔄</button>
            <a class="icon-btn" href="#/login" title="Cài đặt">⚙️</a>
          </div>
        </header>
      )}
      <OfflineBanner />
      <main class="page">{page}</main>
      {!showLogin && (
        <nav class="bottom-nav">
          <a class={hash === "#/orders" || orderMatch ? "tab active" : "tab"} href="#/orders" onClick={() => resetOrdersScroll()}><span class="tab-ico">📋</span><span class="tab-lbl">Đơn</span></a>
          <a class={tab("#/customers")} href="#/customers"><span class="tab-ico">👤</span><span class="tab-lbl">Khách</span></a>
          <a class={tab("#/create")} href="#/create"><span class="tab-ico">➕</span><span class="tab-lbl">Tạo</span></a>
          <a class={tab("#/san_xuat")} href="#/san_xuat"><span class="tab-ico">🏭</span><span class="tab-lbl">SX</span></a>
          <a class={tab("#/kho")} href="#/kho"><span class="tab-ico">📦</span><span class="tab-lbl">Kho</span></a>
          <button class={hash.startsWith("#/bang-gia") ? "tab nav-more active" : "tab nav-more"} onClick={() => setMenuOpen(true)} title="Thêm"><span class="tab-ico">☰</span><span class="tab-lbl">Thêm</span></button>
        </nav>
      )}
      {menuOpen && !showLogin && (
        <div class="modal-overlay" onClick={() => setMenuOpen(false)}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head">Mục khác</div>
            <a class="menu-item" href="#/lich-su" onClick={() => setMenuOpen(false)}>🕘 Lịch sử thao tác</a>
            <a class="menu-item" href="#/bang-gia" onClick={() => setMenuOpen(false)}>💰 Bảng giá chung</a>
          </div>
        </div>
      )}
    </div>
  );
}

render(<App />, document.getElementById("app")!);
