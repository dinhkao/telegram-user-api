// Entry — hash router (#/orders, #/order/:id, #/create, #/customers, #/login)
// + thanh nav dưới + banner offline/hàng đợi. Connects to: pages/*, api.ts.
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { currentUser, replayQueue, serverUrl } from "./api";
import { getQueue } from "./offline";
import { CreateOrder } from "./pages/CreateOrder";
import { Customers } from "./pages/Customers";
import { Login } from "./pages/Login";
import { OrderDetail } from "./pages/OrderDetail";
import { OrdersList } from "./pages/OrdersList";
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

function App() {
  const hash = useHash();
  const user = currentUser();
  // APK load bundle qua WebViewAssetLoader tại appassets.androidplatform.net —
  // trong đó bắt buộc phải có server_url (fetch relative sẽ trỏ nhầm vào assets)
  const inApk = window.location.hostname === "appassets.androidplatform.net" || window.location.protocol === "file:";
  const needSetup = inApk && !serverUrl();
  if ((!user || needSetup) && hash !== "#/login") {
    window.location.hash = "#/login";
    return null;
  }

  let page;
  const orderMatch = hash.match(/^#\/order\/(-?\d+)/);
  if (hash === "#/login") page = <Login />;
  else if (orderMatch) page = <OrderDetail threadId={orderMatch[1]} />;
  else if (hash.startsWith("#/create")) page = <CreateOrder />;
  else if (hash.startsWith("#/customers")) page = <Customers />;
  else page = <OrdersList />;

  const tab = (h: string) => (hash.startsWith(h) ? "tab active" : "tab");
  return (
    <div class="app">
      <OfflineBanner />
      <main class="page">{page}</main>
      {hash !== "#/login" && (
        <nav class="bottom-nav">
          <a class={hash === "#/orders" || orderMatch ? "tab active" : "tab"} href="#/orders">📋 Đơn</a>
          <a class={tab("#/create")} href="#/create">➕ Tạo</a>
          <a class={tab("#/customers")} href="#/customers">👤 Khách</a>
          <a class="tab" href="#/login">⚙️</a>
        </nav>
      )}
    </div>
  );
}

render(<App />, document.getElementById("app")!);
