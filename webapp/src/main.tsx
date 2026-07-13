// Entry — hash router (#/orders, #/order/:id, #/create, #/customers, #/login)
// + thanh nav dưới + banner offline/hàng đợi. Connects to: pages/*, api.ts.
import { render } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { currentUser, getJSON, replayQueue, netOk, onNetStatus, refreshMe, soVN } from "./api";
import { getQueue } from "./offline";
import { getStatus, onStatus, onRealtime, startRealtime, stopRealtime, type RealtimeStatus } from "./realtime";
import { CreateOrder } from "./pages/CreateOrder";
import { Icon } from "./ui/Icon";
import { usePopupBack } from "./ui/usePopupBack";
import { Customers } from "./pages/Customers";
import { CustomerDetail } from "./pages/CustomerDetail";
import { CustomerCalendarPage } from "./pages/CustomerCalendarPage";
import { TasksBoard } from "./pages/TasksBoard";
import { TaskDetail } from "./pages/TaskDetail";
import { PriceLists } from "./pages/PriceLists";
import { PriceListDetail } from "./pages/PriceListDetail";
import { Login } from "./pages/Login";
import { FeedbackHost } from "./ui/feedback";
import { OrderDetail } from "./pages/OrderDetail";
import { OrderInvoiceEdit } from "./pages/OrderInvoiceEdit";
import { OrderPayment } from "./pages/OrderPayment";
import { OrdersList, resetOrdersScroll } from "./pages/OrdersList";
import { fastScrollTop } from "./scroll";
import { DeliveryCalendar } from "./pages/DeliveryCalendar";
import { DeliveringOrders } from "./pages/DeliveringOrders";
import { ActivityLog } from "./pages/ActivityLog";
import { ProductionList } from "./pages/ProductionList";
import { ProductionDetail } from "./pages/ProductionDetail";
import { ProductionReportEdit } from "./pages/ProductionReportEdit";
import { ProductionDashboard } from "./pages/ProductionDashboard";
import { ProductionWorkerDetail } from "./pages/ProductionWorkerDetail";
import { QuyList } from "./pages/QuyList";
import { ReturnsList } from "./pages/ReturnsList";
import { ReturnDetail } from "./pages/ReturnDetail";
import { PurchasesList } from "./pages/PurchasesList";
import { PurchaseDetail } from "./pages/PurchaseDetail";
import { PurchaseEdit } from "./pages/PurchaseEdit";
import { SuppliersList } from "./pages/SuppliersList";
import { SupplierDetail } from "./pages/SupplierDetail";
import { WorkerList } from "./pages/WorkerList";
import { WorkerArrange } from "./pages/WorkerArrange";
import { Home } from "./pages/Home";
import { Users } from "./pages/Users";
import { NotifCenter } from "./NotifCenter";
import { TaskBell } from "./TaskBell";
import { InventoryList } from "./pages/InventoryList";
import { InventoryDetail } from "./pages/InventoryDetail";
import { KhoBoxes } from "./pages/KhoBoxes";
import { StockDemand } from "./pages/StockDemand";
import { CallNumbers } from "./pages/CallNumbers";
import { ProductTimeline } from "./pages/ProductTimeline";
import { WagesDashboard } from "./pages/WagesDashboard";
import { ReportSlips } from "./pages/ReportSlips";
import { ReportSlipDetail } from "./pages/ReportSlipDetail";
import { WageTable } from "./pages/WageTable";
import { BulkMove } from "./pages/BulkMove";
import { PlacesList } from "./pages/PlacesList";
import { PlaceDetail } from "./pages/PlaceDetail";
import { PlaceTimeline } from "./pages/PlaceTimeline";
import { BoxDetail } from "./pages/BoxDetail";
import { BoxTimeline } from "./pages/BoxTimeline";
import { CameraGallery } from "./pages/CameraGallery";
import { UsageStats } from "./pages/UsageStats";
import { DisposalsList } from "./pages/DisposalsList";
import { DisposalDetail } from "./pages/DisposalDetail";
import { initUsage } from "./usage";
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
      const reached = Math.abs(window.scrollY - target) <= 2;
      if (!reached) window.scrollTo(0, target); // chỉ ép khi lệch — ép mỗi frame gây giật cuộn
      const now = performance.now();
      const h = document.documentElement.scrollHeight;
      if (h !== lastH) { lastH = h; stableAt = now; }  // trang còn cao lên (nội dung tải trễ)
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

// Banner DÍNH dưới app-bar — chữ chạy ngang (marquee): "<N> đơn chưa nộp" +
// "<N> thùng chưa xếp kho". Số từ chip stats /api/orders + /api/inventory/
// unplaced-count (2 query nhẹ); cập nhật khi có realtime tương ứng (gộp 3s)
// + poll 2 phút. Cả hai = 0 → ẩn banner.
function NopBanner() {
  const [n, setN] = useState(0);        // đơn đã giao chưa nộp
  const [boxes, setBoxes] = useState(0); // thùng chưa gán vị trí kho
  const [short, setShort] = useState({ n: 0, total: 0 }); // SP thiếu hàng cho đơn hôm nay
  const [pins, setPins] = useState<{ id: number; text: string; href?: string }[]>([]); // bình luận ghim 24h
  const t = useRef<any>(null);
  useEffect(() => {
    const load = () => {
      getJSON("/api/orders?page=1&limit=1", { cache: false })
        .then((d) => setN(Number(d.stats?.chua_nop) || 0))
        .catch(() => {});
      getJSON("/api/inventory/unplaced-count", { cache: false })
        .then((d) => setBoxes(Number(d.count) || 0))
        .catch(() => {});
      getJSON("/api/banner/pins", { cache: false })
        .then((d) => setPins(d.pins || []))
        .catch(() => {});
      getJSON("/api/inventory/demand", { cache: false })
        .then((d) => setShort({ n: Number(d.totals?.short_products) || 0, total: Number(d.totals?.total_shortfall) || 0 }))
        .catch(() => {});
    };
    load();
    const poll = setInterval(load, 120000);
    const off = onRealtime((e) => {
      if (e.type !== "order_changed" && e.type !== "orders_changed" &&
          e.type !== "inventory_changed" && e.type !== "box_changed" &&
          e.type !== "banner_changed") return;
      clearTimeout(t.current);
      t.current = setTimeout(load, e.type === "banner_changed" ? 200 : 3000);
    });
    return () => { clearInterval(poll); clearTimeout(t.current); off(); };
  }, []);
  const show = n > 0 || boxes > 0 || pins.length > 0 || short.n > 0;
  const [open, setOpen] = useState(false); // sheet liệt kê mọi tin trên banner
  usePopupBack(open, () => setOpen(false));
  // Banner chiếm ~28px dưới app-bar → các sticky khác (topbar tìm kiếm, header
  // chi tiết đơn, preview tạo đơn…) phải tụt xuống theo (body.has-nop, styles.css)
  useEffect(() => {
    document.body.classList.toggle("has-nop", show);
    return () => document.body.classList.remove("has-nop");
  }, [show]);
  if (!show) return null;
  // Chạy LIÊN TỤC phải→trái không hở: track = 2 nửa giống hệt (lặp chuỗi tin ×6),
  // animation dịch đúng −50% rồi lặp → nối liền mạch, không thấy khoảng trống.
  // Bình luận ghim = chip ĐỎ (quan trọng, tự hết sau 24h); số liệu thường = chữ
  // trên nền trắng (luôn có, ít quan trọng hơn).
  const hLeft = (exp: number) => {
    const h = (exp * 1000 - Date.now()) / 3600e3;
    return h >= 1 ? `còn ${Math.round(h)}h` : `còn ${Math.max(1, Math.round(h * 60))}p`;
  };
  const parts: { text: string; href: string; pin?: boolean; sub?: string }[] = [];
  for (const p of pins) parts.push({
    text: `📢 ${p.text}`, href: p.href || "#/orders", pin: true,
    sub: `${(p as any).created_by ? `${(p as any).created_by} ghim · ` : ""}${hLeft((p as any).expires_at)}`,
  });
  if (short.n > 0) parts.push({ text: `⚠️ Thiếu hàng: ${short.n} mã (thiếu ${soVN(short.total)})`, href: "#/nhu-cau", pin: true, sub: "bấm để xem Cần làm hàng" });
  if (n > 0) parts.push({ text: `💰 ${n} đơn chưa nộp tiền`, href: "#/orders?filter=chua_nop", sub: "bấm để lọc Chưa nộp" });
  if (boxes > 0) parts.push({ text: `📦 ${boxes} thùng chưa xếp kho`, href: "#/kho", sub: "bấm để mở Kho hàng" });
  // Tốc độ CỐ ĐỊNH (~50px/s) dù nội dung dài ngắn: thời gian tỉ lệ độ rộng nửa
  // track (ước lượng ~7px/ký tự + 48px đệm/mẩu, nửa track = 3 lượt parts).
  const halfPx = 3 * parts.reduce((s, p) => s + p.text.length * 7 + 48, 0);
  const durSec = Math.max(12, Math.round(halfPx / 50));
  // Bấm BẤT KỲ đâu trên banner → mở sheet liệt kê đủ mọi tin (khỏi chờ chữ chạy
  // qua); bấm từng dòng mới đi tới đích. Chữ chạy chỉ để hiển thị.
  return (
    <>
      <button class="nop-banner" aria-label={parts.map((p) => p.text).join(" · ")} onClick={() => setOpen(true)}>
        <span class="nop-marquee" style={{ animationDuration: `${durSec}s` }}>
          {[0, 1, 2, 3, 4, 5].flatMap((i) =>
            parts.map((p, j) => (
              <span class={"nop-seg" + (p.pin ? " pin" : "")} key={`${i}-${j}`}>{p.text}</span>
            )))}
        </span>
      </button>
      {open && (
        <div class="modal-overlay" onClick={() => setOpen(false)}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><b>📋 Bảng tin</b>
              <button class="btn small" onClick={() => setOpen(false)}><Icon name="close" size={14} /></button>
            </div>
            <div class="nop-pop-list">
              {parts.map((p, i) => (
                <a class={"nop-pop-item" + (p.pin ? " pin" : "")} key={i} href={p.href} onClick={() => setOpen(false)}>
                  <span class="nop-pop-text">{p.text}</span>
                  {p.sub && <span class="muted small">{p.sub}</span>}
                  <Icon name="chevronRight" size={16} class="nop-pop-chev" />
                </a>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// Dòng điều phối cố định ngay trên nav: tóm tắt ai đang giữ đơn đi giao.
function DeliveringBanner() {
  const [orders, setOrders] = useState<any[]>([]);
  const [rolling, setRolling] = useState(false);
  const copyRef = useRef<HTMLSpanElement>(null);
  const runRef = useRef<HTMLSpanElement>(null);
  const timer = useRef<any>(null);
  useEffect(() => {
    const load = () => getJSON("/api/orders/delivering", { cache: false })
      .then((d) => setOrders(d.orders || [])).catch(() => {});
    load();
    const poll = setInterval(load, 120000);
    const off = onRealtime((e) => {
      if (e.type !== "order_changed" && e.type !== "orders_changed" && e.type !== "resync") return;
      clearTimeout(timer.current);
      timer.current = setTimeout(load, 1500);
    });
    return () => { clearInterval(poll); clearTimeout(timer.current); off(); };
  }, []);
  useEffect(() => {
    document.body.classList.toggle("has-delivering", orders.length > 0);
    return () => document.body.classList.remove("has-delivering");
  }, [orders.length]);
  const groups = new Map<string, string[]>();
  for (const o of orders) {
    const who = o.delivery_actor || "Chưa rõ";
    const rawCustomer = o.customer_nickname || o.customer || `đơn #${o.thread_id}`;
    const customer = rawCustomer.charAt(0).toUpperCase() + rawCustomer.slice(1);
    groups.set(who, [...(groups.get(who) || []), customer]);
  }
  const summary = [...groups].map(([who, customers]) => `${who} đang giao ${customers.join(", ")}`).join(" · ");
  useEffect(() => {
    const measure = () => {
      const copy = copyRef.current, run = runRef.current;
      if (copy && run) setRolling(run.scrollWidth - 52 > copy.clientWidth + 2);
    };
    const raf = requestAnimationFrame(measure);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    if (copyRef.current) ro?.observe(copyRef.current);
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); };
  }, [summary]);
  if (!orders.length) return null;
  const duration = Math.max(12, Math.round(summary.length * 7 / 40));
  return (
    <a class="delivering-banner" href="#/dang-giao" title={summary}>
      <Icon name="truck" size={15} />
      <span class="delivering-copy" ref={copyRef}>
        <span class={rolling ? "delivering-track rolling" : "delivering-track"}
          style={rolling ? { animationDuration: `${duration}s` } : undefined}>
          <span class="delivering-run" ref={runRef}>{summary}</span>
          {rolling && <span class="delivering-run" aria-hidden="true">{summary}</span>}
        </span>
      </span>
      <Icon name="chevronRight" size={15} />
    </a>
  );
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
  const user = currentUser();
  // Webapp luôn cùng origin với server (APK nạp URL từ xa qua Tailscale) nên không
  // còn màn hình cài server_url — chỉ cần đăng nhập.
  const showLogin = hash === "#/login" || !user;
  const authed = !!user;

  // Đồng bộ role từ server lúc mở app — role cache lúc login có thể CŨ (admin đổi
  // role sau đó, vd cấp quyền văn phòng). Role đổi → ép render lại để nút theo quyền hiện đúng.
  const [, bumpRole] = useState(0);
  useEffect(() => {
    if (!authed) return;
    refreshMe().then((changed) => { if (changed) bumpRole((x) => x + 1); }).catch(() => {});
  }, [authed]);

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

  // KHOÁ CUỘN NỀN khi có popup — quy tắc TOÀN CỤC: hễ có overlay bất kỳ trong DOM
  // thì thêm body.modal-open (overflow:hidden) để nền không cuộn, khỏi phá cuộn
  // trong popup. Tự cover mọi popup hiện tại lẫn tương lai dùng các class overlay này.
  useEffect(() => {
    const SEL = ".modal-overlay, .cf-backdrop, .pv-overlay";
    const update = () => document.body.classList.toggle("modal-open", !!document.querySelector(SEL));
    const mo = new MutationObserver(update);
    mo.observe(document.body, { childList: true, subtree: true });
    update();
    return () => { mo.disconnect(); document.body.classList.remove("modal-open"); };
  }, []);

  // ẨN NAV DƯỚI khi bàn phím MỀM bật. Dò theo FOCUS ô nhập (đáng tin trên Android
  // WebView + iOS): visualViewport không dùng được vì WebView co cả innerHeight theo
  // bàn phím → hiệu số ~0. kbd-open = đang focus ô gõ được (text/số/textarea/CE),
  // loại checkbox/nút. focusout đợi 1 nhịp rồi soi activeElement (khỏi nháy khi nhảy ô).
  useEffect(() => {
    // CHỈ mobile/cảm ứng — desktop (chuột) không ẩn nav khi bấm ô nhập.
    const isTouch = (typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches) || (navigator.maxTouchPoints || 0) > 0;
    if (!isTouch) return;
    const NOKBD = new Set(["checkbox", "radio", "button", "submit", "reset", "file", "range", "color", "image"]);
    const isField = (t: any): boolean => {
      if (!t) return false;
      if (t.isContentEditable) return true;
      if (t.tagName === "TEXTAREA") return true;
      if (t.tagName === "INPUT") return !NOKBD.has(String(t.type || "text").toLowerCase());
      return false;
    };
    const setKbd = () => document.body.classList.toggle("kbd-open", isField(document.activeElement));
    let t: any;
    const onIn = () => { clearTimeout(t); setKbd(); };
    const onOut = () => { clearTimeout(t); t = setTimeout(setKbd, 60); };
    document.addEventListener("focusin", onIn);
    document.addEventListener("focusout", onOut);
    setKbd();

    // Người ẩn bàn phím (nút xuống Android) KHÔNG tự blur ô → ô còn focus, nav vẫn ẩn.
    // Dò bàn phím ĐÓNG qua visualViewport nở lại → blur ô đang focus (→ focusout → nav về).
    const vv = window.visualViewport;
    let maxH = vv?.height || 0, wasOpen = false;
    const onVV = () => {
      if (!vv) return;
      if (vv.height > maxH) maxH = vv.height;
      if (vv.height < maxH - 100) wasOpen = true;            // bàn phím đang mở
      else if (wasOpen) {                                    // nở lại = bàn phím đóng
        wasOpen = false;
        const a = document.activeElement as HTMLElement | null;
        if (isField(a)) a?.blur();
      }
    };
    vv?.addEventListener("resize", onVV);

    return () => {
      document.removeEventListener("focusin", onIn);
      document.removeEventListener("focusout", onOut);
      vv?.removeEventListener("resize", onVV);
      document.body.classList.remove("kbd-open");
    };
  }, []);

  let page;
  const invEditMatch = hash.match(/^#\/order\/(-?\d+)\/hoa-don/);
  const payMatch = hash.match(/^#\/order\/(-?\d+)\/thanh-toan/);
  const orderMatch = hash.match(/^#\/order\/(-?\d+)/);
  const prodEditMatch = hash.match(/^#\/san_xuat\/(-?\d+)\/bao-cao/);
  const baoCaoMatch = hash.match(/^#\/bao-cao\/(\d+)/);
  const shtMatch = hash.match(/^#\/sx-tho\/([^?]+)/);
  const prodMatch = hash.match(/^#\/san_xuat\/(-?\d+)/);
  const khoTLMatch = hash.match(/^#\/kho\/([^/?]+)\/timeline/);
  const khoMatch = hash.match(/^#\/kho\/([^?]+)/);
  const placeTLMatch = hash.match(/^#\/vi-tri\/(\d+)\/timeline/);
  const placeMatch = hash.match(/^#\/vi-tri\/(\d+)/);
  const boxTLMatch = hash.match(/^#\/thung\/(\d+)\/timeline/);
  const boxMatch = hash.match(/^#\/thung\/(\d+)/);
  const viecMatch = hash.match(/^#\/viec\/(\d+)/);
  const retMatch = hash.match(/^#\/tra-hang\/(\d+)/);
  const dispMatch = hash.match(/^#\/xuat-huy\/(\d+)/);
  const purEditMatch = hash.match(/^#\/nhap-hang\/(\d+)\/sua/);
  const purMatch = hash.match(/^#\/nhap-hang\/(\d+)/);
  const nccMatch = hash.match(/^#\/ncc\/(\d+)/);
  const khachLichMatch = hash.match(/^#\/khach\/([^/?]+)\/lich/);
  const khachMatch = hash.match(/^#\/khach\/([^?]+)/);
  const bangGiaMatch = hash.match(/^#\/bang-gia\/([^?]+)/);
  // Deep-link từ notification: ?focus=comment:123 / ?focus=image:45 → cuộn + nháy
  const focusMatch = hash.match(/[?&]focus=([a-z]+):(\d+)/i);
  const focusEl = focusMatch ? `${focusMatch[1]}-${focusMatch[2]}` : undefined;
  useScrollMemory(hash, !!focusEl);
  if (showLogin) page = <Login />;
  else if (invEditMatch) page = <OrderInvoiceEdit threadId={invEditMatch[1]} />;
  else if (payMatch) page = <OrderPayment threadId={payMatch[1]} />;
  else if (orderMatch) page = <OrderDetail threadId={orderMatch[1]} focus={focusEl} />;
  else if (prodEditMatch) page = <ProductionReportEdit threadId={prodEditMatch[1]} />;
  else if (shtMatch) page = <ProductionWorkerDetail name={decodeURIComponent(shtMatch[1])} />;
  else if (hash.startsWith("#/sx-bang")) page = <ProductionDashboard />;
  else if (hash.startsWith("#/tien-cong")) page = <WagesDashboard />;
  else if (baoCaoMatch) page = <ReportSlipDetail id={baoCaoMatch[1]} />;
  else if (hash.startsWith("#/bao-cao")) page = <ReportSlips />;
  else if (hash.startsWith("#/luong-sp")) page = <WageTable />;
  else if (prodMatch) page = <ProductionDetail threadId={prodMatch[1]} focus={focusEl} />;
  else if (hash.startsWith("#/san_xuat")) page = <ProductionList />;
  else if (boxTLMatch) page = <BoxTimeline boxId={boxTLMatch[1]} />;
  else if (boxMatch) page = <BoxDetail boxId={boxMatch[1]} focus={focusEl} />;
  else if (placeTLMatch) page = <PlaceTimeline placeId={placeTLMatch[1]} focus={focusEl} />;
  else if (placeMatch) page = <PlaceDetail id={placeMatch[1]} />;
  else if (hash.startsWith("#/vi-tri")) page = <PlacesList />;
  else if (khoTLMatch) page = <ProductTimeline code={decodeURIComponent(khoTLMatch[1])} focus={focusEl} />;
  else if (khoMatch) page = <InventoryDetail code={decodeURIComponent(khoMatch[1])} />;
  else if (hash.startsWith("#/san-pham")) page = <InventoryList />;
  else if (hash.startsWith("#/nhu-cau")) page = <StockDemand />;
  else if (hash.startsWith("#/so-thung")) page = <CallNumbers />;
  else if (hash.startsWith("#/chuyen-kho")) page = <BulkMove />;
  else if (hash.startsWith("#/kho")) page = <KhoBoxes />;
  else if (hash.startsWith("#/quy")) page = <QuyList />;
  else if (hash.startsWith("#/users")) page = <Users />;
  else if (hash.startsWith("#/tho/sap-xep")) page = <WorkerArrange />;
  else if (hash.startsWith("#/tho")) page = <WorkerList />;
  else if (hash.startsWith("#/lich-su")) page = <ActivityLog />;
  else if (hash.startsWith("#/camera")) page = <CameraGallery />;
  else if (hash.startsWith("#/usage")) page = <UsageStats />;
  else if (hash.startsWith("#/dang-giao")) page = <DeliveringOrders />;
  else if (hash.startsWith("#/lich")) page = <DeliveryCalendar />;
  else if (hash.startsWith("#/create")) page = <CreateOrder />;
  else if (hash.startsWith("#/home")) page = <Home />;
  else if (viecMatch) page = <TaskDetail id={Number(viecMatch[1])} />;
  else if (hash.startsWith("#/viec")) page = <TasksBoard />;
  else if (retMatch) page = <ReturnDetail id={retMatch[1]} />;
  else if (hash.startsWith("#/tra-hang")) page = <ReturnsList />;
  else if (purEditMatch) page = <PurchaseEdit id={purEditMatch[1]} />;
  else if (purMatch) page = <PurchaseDetail id={purMatch[1]} />;
  else if (dispMatch) page = <DisposalDetail id={dispMatch[1]} />;
  else if (hash.startsWith("#/xuat-huy")) page = <DisposalsList />;
  else if (hash.startsWith("#/nhap-hang")) page = <PurchasesList />;
  else if (nccMatch) page = <SupplierDetail id={nccMatch[1]} />;
  else if (hash.startsWith("#/ncc")) page = <SuppliersList />;
  else if (khachLichMatch) page = <CustomerCalendarPage ckey={decodeURIComponent(khachLichMatch[1])} />;
  else if (khachMatch) page = <CustomerDetail ckey={decodeURIComponent(khachMatch[1])} />;
  else if (hash.startsWith("#/customers")) page = <Customers />;
  else if (bangGiaMatch) page = <PriceListDetail listId={decodeURIComponent(bangGiaMatch[1])} />;
  else if (hash.startsWith("#/bang-gia")) page = <PriceLists />;
  else page = <OrdersList />;

  const tab = (h: string) => (hash.startsWith(h) ? "tab active" : "tab");
  // Tiêu đề app-bar theo route (thay tiêu đề cố định "Đơn hàng" mọi trang)
  const isHome = !showLogin && (hash === "" || hash === "#/" || hash.startsWith("#/orders")) && !orderMatch;
  const pageTitle =
    invEditMatch ? "Sửa hoá đơn"
    : orderMatch ? "Chi tiết đơn"
    : hash.startsWith("#/tra-hang") ? "Trả hàng"
    : purEditMatch ? "Sửa phiếu nhập"
    : hash.startsWith("#/xuat-huy") ? "Xuất hủy"
    : hash.startsWith("#/nhap-hang") ? "Nhập hàng"
    : hash.startsWith("#/ncc") ? "Nhà cung cấp"
    : (hash.startsWith("#/customers") || khachMatch) ? "Khách hàng"
    : hash.startsWith("#/create") ? "Tạo đơn"
    : hash.startsWith("#/home") ? "Trang chủ"
    : hash.startsWith("#/tien-cong") ? "Tiền công"
    : hash.startsWith("#/bao-cao") ? "Báo cáo SX"
    : hash.startsWith("#/luong-sp") ? "Lương SP"
    : (hash.startsWith("#/san_xuat") || hash.startsWith("#/sx-") || prodMatch || prodEditMatch || shtMatch) ? "Sản xuất"
    : hash.startsWith("#/san-pham") ? "Sản phẩm"
    : hash.startsWith("#/nhu-cau") ? "Cần làm hàng"
    : hash.startsWith("#/so-thung") ? "Số thùng"
    : hash.startsWith("#/chuyen-kho") ? "Chuyển kho"
    : (hash.startsWith("#/vi-tri") || placeMatch) ? "Vị trí kho"
    : khoTLMatch ? "Biến động tồn"
    : (hash.startsWith("#/kho") || khoMatch || boxMatch) ? "Kho hàng"
    : hash.startsWith("#/viec") ? "Việc"
    : hash.startsWith("#/quy") ? "Sổ quỹ"
    : hash.startsWith("#/users") ? "Người dùng"
    : hash.startsWith("#/tho") ? "Thợ"
    : hash.startsWith("#/lich-su") ? "Lịch sử thao tác"
    : hash.startsWith("#/camera") ? "Camera 2026"
    : hash.startsWith("#/usage") ? "Thống kê sử dụng"
    : hash.startsWith("#/dang-giao") ? "Ai đang giao"
    : hash.startsWith("#/lich") ? "Lịch giao"
    : (hash.startsWith("#/bang-gia") || bangGiaMatch) ? "Bảng giá"
    : "Đơn hàng";
  return (
    <div class="app">
      <FeedbackHost />
      {!showLogin && (
        <header class="app-bar">
          <span class="app-title">{isHome && <span class="app-logo" aria-hidden="true">🍬</span>}{pageTitle}</span>
          <div class="app-bar-right">
            <RealtimeDot />
            <TaskBell />
            <NotifCenter />
            <button class="icon-btn" title="Tải lại" onClick={() => window.location.reload()}><Icon name="refresh" size={19} /></button>
            <a class="icon-btn" href="#/login" title="Cài đặt"><Icon name="settings" size={19} /></a>
          </div>
        </header>
      )}
      <OfflineBanner />
      {!showLogin && <NopBanner />}
      <main class="page">{page}</main>
      {!showLogin && (
        <div class="bottom-dock">
          {isHome && <DeliveringBanner />}
          <nav class="bottom-nav">
          <a class={hash === "#/orders" || orderMatch ? "tab active" : "tab"} href="#/orders" onClick={() => resetOrdersScroll()}><Icon name="clipboard" size={22} class="tab-ico" /><span class="tab-lbl">Đơn</span></a>
          <a class={tab("#/customers")} href="#/customers" onClick={() => fastScrollTop()}><Icon name="user" size={22} class="tab-ico" /><span class="tab-lbl">Khách</span></a>
          <a class={tab("#/create")} href="#/create" onClick={() => fastScrollTop()}><Icon name="plus" size={22} class="tab-ico" /><span class="tab-lbl">Tạo</span></a>
          <a class={tab("#/san_xuat")} href="#/san_xuat" onClick={() => fastScrollTop()}><Icon name="factory" size={22} class="tab-ico" /><span class="tab-lbl">SX</span></a>
          <a class={tab("#/kho")} href="#/kho" onClick={() => fastScrollTop()}><Icon name="box" size={22} class="tab-ico" /><span class="tab-lbl">Kho</span></a>
          <a class={hash.startsWith("#/home") ? "tab nav-more active" : "tab nav-more"} href="#/home" title="Thêm" onClick={() => fastScrollTop()}><Icon name="menu" size={22} class="tab-ico" /><span class="tab-lbl">Thêm</span></a>
          </nav>
        </div>
      )}
    </div>
  );
}

render(<App />, document.getElementById("app")!);
initUsage();
