// Danh sách đơn — search (FTS server), lọc xong/chưa, phân trang "Tải thêm".
// Data: GET /api/orders (server_app/orders_api.py). Card → #/order/:thread_id.
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { isRecent } from "../format";

import { onRealtime } from "../realtime";
import { listOrderImages, type OrderImage } from "../api";
import { PhotoViewer } from "../detail/PhotoViewer";
import {
  type OrderRow, statusLabel, Highlight, InvoiceMini, LastAction,
  groupOrdersByDay, UltraBody, CardBody, CompactBody, NEW_ORDER_SEC, orderAllDone,
} from "../detail/OrderCards";
import { Loading, EmptyState, SkeletonList } from "../ui/states";
import { Icon } from "../ui/Icon";
import { SearchBar, FilterActiveBar } from "../ui/SearchBar";
import { fastScrollTop } from "../scroll";



type FilterKey = "all" | "pending" | "done" | "chua_soan" | "chua_giao" | "chua_nop" | "chua_nhan" | "no";
type SortKey = "created" | "updated" | "ngay_giao" | "giao_at";
const PAGE_SIZE = 20; // luôn tải 20 mỗi lần, kể cả lần đầu — không bao giờ tải hết
const FILTER_LABELS: Record<string, string> = {
  pending: "Chưa xong", done: "Đã xong",
  chua_soan: "Chưa soạn", chua_giao: "Chưa giao", chua_nop: "Chưa nộp", chua_nhan: "Chưa nhận",
  no: "Còn nợ",
};

// Dòng còn KHỚP chip lọc đang chọn không? Khớp đúng semantics server
// (server_app/orders_api.py): chua_* theo cờ workflow, pending/done theo
// done_after_20250124. Dùng khi vá dòng realtime: đơn flip trạng thái →
// không còn khớp filter → phải RÚT khỏi danh sách (không chỉ vá tại chỗ).
/** Ngày giao ≤ hôm nay (hoặc chưa hẹn) — khớp rule 'Chưa giao' của server. */
function giaoDue(o: OrderRow): boolean {
  const ng = ((o as any).ngay_giao || "").slice(0, 10);
  if (!ng) return true;
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return ng <= today;
}

/** Số trên ô lọc: gọn cho số lớn (15973 → "16k") để 5 ô luôn vừa 1 hàng. */
function fmtChipCount(n: number): string {
  return n >= 1000 ? `${Math.round(n / 1000)}k` : String(n);
}

function rowMatchesFilter(o: OrderRow, f: FilterKey): boolean {
  switch (f) {
    case "chua_soan": return !o.soan;
    case "chua_giao": return !o.giao && giaoDue(o);   // bỏ đơn hẹn giao tương lai
    case "chua_nop": return !o.nop && !!o.giao; // chưa nộp = ĐÃ giao nhưng chưa nộp
    case "chua_nhan": return !o.nhan && !!o.nop; // chưa nhận = ĐÃ nộp nhưng chưa nhận
    case "no": return [...(o.task_icons || "")][5] === "😡"; // còn nợ = chưa có thanh toán nào
    case "pending": return !o.done_after_20250124;
    case "done": return !!o.done_after_20250124;
    default: return true; // "all"
  }
}

// Cache toàn danh sách + vị trí cuộn — sống ở module scope nên vẫn còn khi
// rời trang chi tiết rồi quay lại (mount lại). Reset khi có search mới.
let listCache: {
  orders: OrderRow[]; stats: any; search: string;
  filter: FilterKey; sort: SortKey; page: number; totalPages: number; stale?: boolean;
} | null = null;

export type FilterNeighbors = {
  prev: number | null; next: number | null;
  prevOrder: OrderRow | null; nextOrder: OrderRow | null;
};

// filterNeighbors đọc cache cấp-module nên bản thân nó không làm component render lại.
// OrderDetail đăng ký listener này để thanh nav đổi ngay khi realtime vá/xoá cache.
const filterNeighborListeners = new Set<() => void>();
const notifyFilterNeighborsChanged = () => filterNeighborListeners.forEach((listener) => {
  try { listener(); } catch { /* một màn lỗi không được chặn listener khác */ }
});

export function onFilterNeighborsChanged(listener: () => void): () => void {
  filterNeighborListeners.add(listener);
  return () => filterNeighborListeners.delete(listener);
}

// Sort trước khi chip "Chưa giao" auto-chuyển sang ngày giao — rời filter thì trả lại.
// Module-scope để sống qua unmount (vào chi tiết rồi quay lại vẫn nhớ).
let autoSortPrev: "created" | "updated" | null = null;

/** No-op giữ lại cho tương thích. Freshness của cache khi danh sách ĐANG UNMOUNT
 *  (người dùng ở trang chi tiết) do subscriber cấp-module bên dưới lo. */
export function invalidateListCache() {
  /* no-op */
}

/** Đơn liền trước/sau trong DANH SÁCH đang lọc (cache module) — cho thanh điều hướng
 *  ở trang chi tiết. Null nếu chưa có cache (mở đơn qua deep-link, không từ danh sách). */
export function filterNeighbors(threadId: string | number): FilterNeighbors {
  if (!listCache) return { prev: null, next: null, prevOrder: null, nextOrder: null };
  const i = listCache.orders.findIndex((o) => String(o.thread_id) === String(threadId));
  if (i < 0) return { prev: null, next: null, prevOrder: null, nextOrder: null };
  const prevOrder = i > 0 ? listCache.orders[i - 1] : null;
  const nextOrder = i < listCache.orders.length - 1 ? listCache.orders[i + 1] : null;
  return {
    prev: prevOrder?.thread_id ?? null,
    next: nextOrder?.thread_id ?? null,
    prevOrder,
    nextOrder,
  };
}

// Đơn mới/xoá hoặc WebSocket vừa nối lại có thể đổi cả quan hệ prev/next. Tải lại
// đúng số trang user đã mở, nhưng vẫn giữ cache cũ trên màn hình trong lúc chờ.
let cachedListRefreshSeq = 0;
async function refreshCachedList(): Promise<void> {
  if (!listCache) return;
  const seq = ++cachedListRefreshSeq;
  const snapshot = { ...listCache, stale: true };
  listCache = snapshot;
  const fp = snapshot.filter !== "all" ? `&filter=${snapshot.filter}` : "";
  const sp = snapshot.sort !== "created" ? `&sort=${snapshot.sort}` : "";
  try {
    const pages = await Promise.all(Array.from({ length: Math.max(1, snapshot.page) }, (_, index) =>
      getJSON(`/api/orders?page=${index + 1}&limit=${PAGE_SIZE}&search=${encodeURIComponent(snapshot.search)}${fp}${sp}`, { cache: false }),
    ));
    const current = listCache;
    // User đã đổi search/filter/sort hoặc tải thêm trang trong lúc request chạy.
    if (seq !== cachedListRefreshSeq || !current || current.search !== snapshot.search || current.filter !== snapshot.filter
      || current.sort !== snapshot.sort || current.page !== snapshot.page) return;
    const first = pages[0] || {};
    listCache = {
      ...current,
      orders: pages.flatMap((page) => page.orders || []),
      stats: first.stats && Object.keys(first.stats).length ? first.stats : current.stats,
      totalPages: first.total_pages || 1,
      stale: false,
    };
    notifyFilterNeighborsChanged();
  } catch {
    // Mất mạng: giữ nav gần nhất; khi quay lại danh sách, cờ stale sẽ buộc refetch.
  }
}

// FIX: khi ở trang chi tiết, OrdersList unmount nên handler realtime của nó KHÔNG
// nhận event → sửa task (vd nhận tiền) xong quay lại vẫn thấy dữ liệu cũ (cache).
// Subscriber cấp-module này LUÔN sống → vá listCache dù danh sách đang unmount, nên
// khi quay lại vẽ từ cache đã là dòng mới. (Lúc mounted, component tự vá state; đây
// chỉ đồng bộ cache — hội tụ cùng giá trị.)
onRealtime((e) => {
  if (e.type === "orders_changed" || e.type === "resync") {
    void refreshCachedList();
    return;
  }
  if (e.type !== "order_changed" || !listCache) return;
  const idx = listCache.orders.findIndex((o) => String(o.thread_id) === e.thread_id);
  let changed = false;
  if (e.row === null) {
    if (idx >= 0) {
      listCache = { ...listCache, orders: listCache.orders.filter((_, i) => i !== idx) };
      changed = true;
    }
  } else if (idx >= 0) {
    // Dòng đổi có thể HẾT khớp chip lọc đang cache (vd lọc "Chưa nhận" mà đơn
    // vừa được nhận ở trang chi tiết) → rút khỏi danh sách thay vì vá tại chỗ.
    if (rowMatchesFilter(e.row as OrderRow, listCache.filter)) {
      const next = listCache.orders.slice();
      next[idx] = e.row as OrderRow;
      listCache = { ...listCache, orders: next };
      changed = true;
    } else {
      listCache = { ...listCache, orders: listCache.orders.filter((_, i) => i !== idx) };
      changed = true;
    }
  }
  if (changed) notifyFilterNeighborsChanged();
});

/** Bấm tab Đơn khi ĐANG ở trang Đơn → cuộn lên đầu (hashchange không xảy ra nên hệ
 *  cuộn trung tâm không tự lo). Điều hướng bình thường do main.tsx quản. */
export function resetOrdersScroll() {
  fastScrollTop();
}

// Đơn cuối cùng người dùng mở — để tô sáng trên dashboard khi quay lại.
export function markLastOrder(id: string | number) {
  try { localStorage.setItem("last_order", String(id)); } catch { /* ignore */ }
}
function getLastOrder(): string {
  try { return localStorage.getItem("last_order") || ""; } catch { return ""; }
}

export function OrdersList() {
  const searchInput = useRef<HTMLInputElement>(null);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [stale, setStale] = useState(false);
  const [err, setErr] = useState("");
  // 3 kiểu xem: full (chi tiết) · compact (gọn) · ultra (siêu gọn: 5 icon + 1 dòng text)
  const [view, setView] = useState<"full" | "compact" | "ultra">(() => {
    const v = localStorage.getItem("dash_view");
    if (v === "compact" || v === "ultra" || v === "full") return v;
    return localStorage.getItem("dash_compact") === "1" ? "compact" : "full"; // back-compat
  });
  // Đổi kiểu xem GIỮ VỊ TRÍ: neo vào đơn trên cùng đang hiện (top-most visible), đổi
  // view rồi cuộn để đơn đó về đúng chỗ cũ → các đơn đang xem vẫn trên màn hình.
  const setViewMode = (m: "full" | "compact" | "ultra") => {
    if (m === view) return;
    let anchor: { oid: string; top: number } | null = null;
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(".order-card[data-oid]"))) {
      const r = el.getBoundingClientRect();
      if (r.bottom > 120) { anchor = { oid: el.dataset.oid!, top: r.top }; break; } // đơn đầu còn dưới app-bar
    }
    localStorage.setItem("dash_view", m);
    setView(m);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (!anchor) return;
      const el = document.querySelector<HTMLElement>(`.order-card[data-oid="${anchor.oid}"]`);
      if (el) window.scrollBy(0, el.getBoundingClientRect().top - anchor.top);
    }));
  };
  const _VIEWS = [
    { m: "full" as const, ic: "☰", t: "Chi tiết" },
    { m: "compact" as const, ic: "≣", t: "Gọn" },
    { m: "ultra" as const, ic: "▬", t: "Siêu gọn" },
  ];
  const [sort, setSort] = useState<SortKey>(() => {
    const s = localStorage.getItem("dash_sort");
    return s === "updated" || s === "ngay_giao" || s === "giao_at" ? s : "created";
  });
  const sortRef = useRef(sort); // đọc trong load (tránh stale closure)
  const changeSort = (s: SortKey) => {
    if (s === sortRef.current) return;
    autoSortPrev = null; // user tự chọn sort → thôi auto-trả-lại khi rời "Chưa giao"
    sortRef.current = s;
    localStorage.setItem("dash_sort", s);
    setSort(s);
    setPage(1);
    listCache = null; // đổi sort → bỏ cache cũ để không vẽ lại danh sách cũ
    load(1, search, filter, false);
  };
  const [flashing, setFlashing] = useState<Record<string, string>>({});
  // Xem ảnh phóng to khi bấm thumbnail trên card (không vào trang chi tiết)
  const [viewer, setViewer] = useState<{ threadId: string; images: OrderImage[]; start: number } | null>(null);
  const openThumb = async (e: Event, o: OrderRow, atId?: number) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      const imgs = await listOrderImages(o.thread_id);
      if (!imgs.length) return;
      const start = Math.max(0, imgs.findIndex((x) => x.id === (atId ?? o.thumb_image_id)));
      setViewer({ threadId: String(o.thread_id), images: imgs, start });
    } catch { /* mất mạng — bỏ qua, vẫn có thể mở đơn */ }
  };
  const flashOrder = async (tid: string) => {
    let msg = "Vừa cập nhật";
    try {
      const r = await getJSON(`/api/order/${tid}/history`, { cache: false });
      const h = (r.history || [])[0];
      if (h) msg = `${h.actor || "?"}: ${h.action}${h.detail ? ` — ${h.detail}` : ""}`;
    } catch { /* ignore */ }
    setFlashing((f) => ({ ...f, [tid]: msg }));
    const id = window.setTimeout(() => setFlashing((f) => { const n = { ...f }; delete n[tid]; return n; }), 5000);
    flashTimers.current.push(id);
  };
  const reqSeq = useRef(0); // "query mới nhất thắng" — bỏ debounce nhưng chặn race
  const flashTimers = useRef<number[]>([]);
  useEffect(() => () => flashTimers.current.forEach(clearTimeout), []); // dọn timer nháy khi rời trang
  const sentinel = useRef<HTMLDivElement>(null);
  // refs giữ state mới nhất cho observer (tránh stale closure)
  const st = useRef<any>({});
  st.current = { page, totalPages, loading, search, filter, sort, orders, stats };

  const load = async (p: number, q: string, f: string, append: boolean) => {
    const seq = ++reqSeq.current; // đánh dấu request này là mới nhất
    setLoading(true);
    setErr("");
    try {
      // filter=all → không gửi (server mặc định all). Lọc pending/done server-side.
      const fp = f && f !== "all" ? `&filter=${f}` : "";
      const sp = sortRef.current !== "created" ? `&sort=${sortRef.current}` : "";
      // chỉ cache trang không search — kết quả theo phím gõ không rác localStorage
      const data = await getJSON(`/api/orders?page=${p}&limit=${PAGE_SIZE}&search=${encodeURIComponent(q)}${fp}${sp}`, { cache: !q });
      if (seq !== reqSeq.current) return; // đã có query mới hơn → bỏ kết quả cũ (chống race)
      setOrders((prev) => (append ? [...prev, ...(data.orders || [])] : (data.orders || [])));
      setTotalPages(data.total_pages || 1);
      if (data.stats && Object.keys(data.stats).length) setStats(data.stats);
      setStale(!!data._stale);
    } catch (ex: any) {
      if (seq === reqSeq.current) setErr(ex.message);
    } finally {
      if (seq === reqSeq.current) setLoading(false);
    }
  };

  // Làm mới CHỈ số đếm chip (Chưa soạn/giao/nộp/nhận) — khi vá 1 dòng tại chỗ, số đếm
  // dễ lệch. Lấy nhẹ page=1&limit=1 (stats tính riêng, không đụng danh sách/vị trí cuộn).
  const statsTimer = useRef<any>(null);
  const refreshStats = () => {
    clearTimeout(statsTimer.current);
    statsTimer.current = setTimeout(async () => {
      try {
        const { search: q, filter: f } = st.current;
        const fp = f && f !== "all" ? `&filter=${f}` : "";
        const data = await getJSON(`/api/orders?page=1&limit=1&search=${encodeURIComponent(q)}${fp}`, { cache: false });
        if (data.stats && Object.keys(data.stats).length) setStats(data.stats);
      } catch { /* im lặng */ }
    }, 400);
  };

  // Deep-link chip lọc: #/orders?filter=chua_nop (banner "đơn chưa nộp") → mở đúng
  // chip. Trả về true nếu đã áp — mount effect bên dưới khỏi khôi phục cache đè lên.
  const applyHashFilter = (): boolean => {
    const fm = window.location.hash.match(/^#\/orders\?filter=([a-z_]+)$/);
    if (!fm || !(fm[1] in FILTER_LABELS)) return false;
    history.replaceState(null, "", "#/orders"); // xoá query — back/refresh không ép lọc lại
    const f = fm[1] as FilterKey;
    listCache = null;
    setSearch("");
    setFilter(f);
    setPage(1);
    load(1, "", f, false);
    return true;
  };
  // Đang MỞ sẵn trang đơn mà bấm link banner → không remount, chỉ có hashchange
  useEffect(() => {
    const onHash = () => { applyHashFilter(); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (applyHashFilter()) return; // vào thẳng từ banner/deep-link
    // Customers page có thể gửi sẵn từ khoá qua pending_search
    const pending = localStorage.getItem("pending_search") || "";
    if (pending) {
      localStorage.removeItem("pending_search");
      listCache = null; // search mới → bỏ cache cũ
      setSearch(pending);
      load(1, pending, "all", false);
      return;
    }
    if (listCache) {
      // Quay lại → vẽ NGAY toàn bộ list đã tải từ cache (giữ nguyên số trang) → trang đủ
      // cao, hệ cuộn trung tâm khôi phục vị trí 1 phát, KHÔNG refetch (tránh co list về
      // trang 1 rồi phải cuộn/tải lại dần). Realtime lo cập nhật khi đang mở.
      const c = listCache;
      setOrders(c.orders);
      setStats(c.stats);
      setSearch(c.search);
      setFilter(c.filter);
      sortRef.current = c.sort;
      setSort(c.sort);
      setPage(c.page);
      setTotalPages(c.totalPages);
      if (c.stale) {
        load(1, c.search, c.filter, false);
        return;
      }
      // Số đếm chip trong cache có thể đã lệch (đơn flip trạng thái lúc trang
      // unmount) → làm mới nhẹ nền (không đụng danh sách/vị trí cuộn).
      refreshStats();
      return;
    }
    load(1, "", "all", false);
  }, []);

  // Lưu snapshot khi rời trang (unmount) — dùng lại khi quay lại
  useEffect(() => {
    return () => {
      const s = st.current;
      if (!s.orders?.length) return;
      listCache = {
        orders: s.orders, stats: s.stats, search: s.search, filter: s.filter, sort: s.sort,
        page: s.page, totalPages: s.totalPages,
      };
    };
  }, []);

  // Realtime: đơn đổi → vá dòng tại chỗ (khỏi refetch); đơn mới/nối lại → tải lại
  // trang 1 theo search+filter hiện tại. Đọc st.current cho giá trị mới nhất.
  useEffect(() => {
    return onRealtime((e) => {
      if (e.type === "orders_changed" || e.type === "resync") {
        setPage(1);
        load(1, st.current.search, st.current.filter, false);
        return;
      }
      if (e.type !== "order_changed") return;
      const tid = e.thread_id;
      let patched = false;
      setOrders((prev) => {
        const idx = prev.findIndex((o) => String(o.thread_id) === tid);
        let next = prev;
        if (e.row === null) {
          if (idx < 0) return prev;
          next = prev.filter((_, i) => i !== idx); // đơn bị xoá
        } else if (idx >= 0) {
          if (rowMatchesFilter(e.row as OrderRow, st.current.filter)) {
            next = prev.slice();
            next[idx] = e.row as OrderRow; // vá dòng đã đổi
            patched = true;
          } else {
            next = prev.filter((_, i) => i !== idx); // hết khớp chip lọc → rút khỏi list
          }
        } else {
          return prev; // chưa có trong danh sách hiện tại → hiện ở lần tải sau
        }
        if (listCache) listCache = { ...listCache, orders: next }; // đồng bộ cache module
        return next;
      });
      if (patched) flashOrder(tid); // nháy sáng + hiện thao tác vừa xảy ra
      refreshStats(); // số đếm chip có thể đổi (đơn flip trạng thái) → cập nhật
    });
  }, []);

  // Infinite scroll: khi sentinel lọt vào khung nhìn → tải trang kế
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      if (!entries[0].isIntersecting) return;
      const { page: p, totalPages: tp, loading: ld, search: q, filter: f } = st.current;
      if (ld || p >= tp) return;
      const next = p + 1;
      setPage(next);
      load(next, q, f, true);
    }, { rootMargin: "300px" }); // tải sớm trước khi chạm đáy
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Tự LẤP ĐẦY: nếu trang chưa đủ cao (sentinel còn trong tầm) mà còn trang → tải tiếp.
  // IntersectionObserver chỉ bắn khi ĐỔI trạng thái; view siêu gọn ngắn nên sentinel hiện
  // sẵn từ đầu → observer bắn 1 lần lúc totalPages chưa kịp cập nhật rồi thôi. Effect này
  // chạy lại mỗi khi orders/totalPages/view/loading đổi để nạp tới khi kín màn hình.
  useEffect(() => {
    const { page: p, totalPages: tp, loading: ld, search: q, filter: f } = st.current;
    if (ld || p >= tp) return;
    const el = sentinel.current;
    if (el && el.getBoundingClientRect().top < window.innerHeight + 300) {
      const next = p + 1;
      setPage(next);
      load(next, q, f, true);
    }
  }, [orders, totalPages, view, loading]);

  const onSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    load(1, q, st.current.filter, false); // gõ tới đâu tìm tới đó — không delay (reqSeq chặn race)
  };

  // Lọc nhanh theo khách: bấm nút cạnh tên khách trên card → đặt ô tìm = tên khách
  // (dùng luôn FTS server). Chặn link card + cuộn lên đầu để thấy kết quả.
  const filterByCustomer = (e: Event, name: string) => {
    e.preventDefault();
    e.stopPropagation();
    onSearch(name);
    window.scrollTo({ top: 0, behavior: "auto" });
  };

  // Đổi chip → reset trang, tải lại từ server với filter mới (nhất quán phân trang)
  const onFilter = (f: FilterKey) => {
    setFilter(f);
    setPage(1);
    // Lọc "Chưa giao" → tự sắp theo NGÀY GIAO; RỜI filter này → trả lại sort trước đó.
    // Không ghi localStorage — auto-switch chỉ trong phiên, không đổi mặc định của user.
    if (f === "chua_giao" && sortRef.current !== "ngay_giao") {
      autoSortPrev = sortRef.current === "updated" ? "updated" : "created";
      sortRef.current = "ngay_giao";
      setSort("ngay_giao");
      listCache = null;
    } else if (f !== "chua_giao" && autoSortPrev && sortRef.current === "ngay_giao") {
      sortRef.current = autoSortPrev;
      setSort(autoSortPrev);
      autoSortPrev = null;
      listCache = null;
    }
    load(1, search, f, false);
  };

  // Đang lọc? (có search hoặc chip khác "tất cả") → cho phép bỏ lọc về mặc định
  const anyFilter = search.trim() !== "" || filter !== "all";
  const clearFilters = () => {
    setSearch("");
    setFilter("all");
    setPage(1);
    if (autoSortPrev && sortRef.current === "ngay_giao") { // bỏ lọc = rời "Chưa giao" → trả sort cũ
      sortRef.current = autoSortPrev;
      setSort(autoSortPrev);
      autoSortPrev = null;
      listCache = null;
    }
    load(1, "", "all", false);
  };

  // Desktop: Esc lần đầu bỏ mọi filter; khi đã sạch, Esc tiếp theo đưa con trỏ vào tìm kiếm.
  useEffect(() => {
    const onEscape = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || !window.matchMedia("(min-width: 720px)").matches || viewer) return;
      e.preventDefault();
      if (st.current.search.trim() || st.current.filter !== "all") {
        clearFilters();
        return;
      }
      searchInput.current?.focus();
      searchInput.current?.select();
    };
    window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  }, [viewer]);

  const visible = orders;
  const lastOrder = getLastOrder(); // đơn vừa mở → tô sáng khi quay lại dashboard
  // Nhịp 60s để tag "Mới" tự hết sau 5 phút (không cần event khác)
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 60000);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <header class="topbar">
        <div class="topbar-row">
          <SearchBar inputRef={searchInput} value={search} onInput={onSearch} placeholder="Tìm khách, sản phẩm…" />
          <div class="view-slider" role="group" aria-label="Kiểu xem">
            {_VIEWS.map((v) => (
              <button key={v.m} class={view === v.m ? "vs-seg on" : "vs-seg"} title={v.t} aria-pressed={view === v.m} onClick={() => setViewMode(v.m)}>{v.ic}</button>
            ))}
            <a class="vs-seg" title="Lịch giao" href="#/lich"><Icon name="calendar" size={14} /></a>
          </div>
        </div>
        {anyFilter && (
          <FilterActiveBar
            parts={[
              filter !== "all" && (FILTER_LABELS[filter] || filter),
              filter === "chua_giao" && "ẩn đơn hẹn giao tương lai",
              filter === "chua_nhan" && "đã nộp, chờ nhận",
              filter === "no" && "chưa có thanh toán nào",
              search.trim() && `“${search.trim()}”`,
            ]}
            count={filter !== "all" && stats ? (stats as any)[filter] : null}
            onClear={clearFilters} />
        )}
      </header>
      {stats && (
        <div class="of-tabs">
          {([
            ["all", "Tất cả", undefined],
            ["chua_soan", "Chưa soạn", stats.chua_soan],
            ["chua_giao", "Chưa giao", stats.chua_giao],
            ["chua_nop", "Chưa nộp", stats.chua_nop],
            ["chua_nhan", "Chưa nhận", stats.chua_nhan],
            ["no", "Nợ 😡", stats.no],
          ] as [FilterKey, string, number | undefined][]).map(([k, lbl, n]) => (
            <button key={k} class={"of-tab" + (filter === k ? " on" : "")} aria-pressed={filter === k} onClick={() => onFilter(k)}>
              {k !== "all" && <b class={"of-n" + (n ? " hot" : "")}>{n != null ? fmtChipCount(n) : "–"}</b>}
              <span class={"of-lbl" + (k === "all" ? " of-lbl-all" : "")}>{lbl}</span>
            </button>
          ))}
        </div>
      )}
      <div class="sort-row">
        <span class="sort-lbl">Sắp xếp:</span>
        <button class={sort === "created" ? "sort-opt active" : "sort-opt"} onClick={() => changeSort("created")}>Mới tạo</button>
        <button class={sort === "updated" ? "sort-opt active" : "sort-opt"} onClick={() => changeSort("updated")}>Mới cập nhật</button>
        <button class={sort === "ngay_giao" ? "sort-opt active" : "sort-opt"} onClick={() => changeSort("ngay_giao")}>Ngày hẹn giao</button>
        <button class={sort === "giao_at" ? "sort-opt active" : "sort-opt"} onClick={() => changeSort("giao_at")}>Ngày giao</button>
      </div>
      {stale && <p class="muted small">⚠️ Dữ liệu lưu sẵn (mất mạng)</p>}
      {err && <p class="error">{err}</p>}
      {loading && !visible.length && <SkeletonList rows={5} />}
      <ul class="order-list">
        {view === "ultra" && groupOrdersByDay(visible, sort).map((g) => (
          <li key={`g-${g.key}`} class="order-day-group">
            <div class="order-day-head">{g.label} <span class="muted small">({g.orders.length})</span></div>
            <ul class="order-list">
              {g.orders.map((o) => (
                <li key={o.thread_id}>
                  <a data-oid={o.thread_id} class={`order-card ultra${orderAllDone(o) ? " all-done" : ""}${String(o.thread_id) === lastOrder ? " last-visited" : ""}`} href={`#/order/${o.thread_id}`}>
                    <UltraBody o={o} search={search} />
                  </a>
                </li>
              ))}
            </ul>
          </li>
        ))}
        {view === "compact" && visible.map((o) => {
          const isNew = isRecent(o.created, NEW_ORDER_SEC);
          return (
          <li key={o.thread_id}>
            <a data-oid={o.thread_id} class={`order-card compact${orderAllDone(o) ? " all-done" : ""}${flashing[String(o.thread_id)] ? " flash" : ""}${String(o.thread_id) === lastOrder ? " last-visited" : ""}${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
              <CompactBody o={o} search={search} sort={sort} flashMsg={flashing[String(o.thread_id)]} isNew={isNew} openThumb={openThumb} />
            </a>
          </li>
          );
        })}
        {view === "full" && visible.map((o) => {
          const stt = statusLabel(o);
          const isNew = isRecent(o.created, NEW_ORDER_SEC);
          return (
          <li key={o.thread_id}>
            <a data-oid={o.thread_id} class={`order-card two-col${orderAllDone(o) ? " all-done" : ""}${flashing[String(o.thread_id)] ? " flash" : ""}${String(o.thread_id) === lastOrder ? " last-visited" : ""}${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
              <div class="card-main">
                {sort === "updated" && <LastAction o={o} />}
                {flashing[String(o.thread_id)] && <div class="flash-msg">🔔 {flashing[String(o.thread_id)]}</div>}
                <CardBody o={o} search={search} stt={stt} isNew={isNew} openThumb={openThumb} filterByCustomer={filterByCustomer} />
              </div>
              <div class="card-inv"><InvoiceMini o={o} q={search} /></div>
            </a>
          </li>
          );
        })}
      </ul>
      {loading && visible.length > 0 && <Loading />}
      {/* sentinel cho infinite scroll — observer tải trang kế khi lọt khung nhìn */}
      <div ref={sentinel} style="height:1px" />
      {!loading && page >= totalPages && visible.length > 0 && (
        <p class="muted center small">— Hết đơn —</p>
      )}
      {!loading && !visible.length && !err && <EmptyState>Không có đơn nào</EmptyState>}
      {viewer && (
        <PhotoViewer
          images={viewer.images}
          start={viewer.start}
          base={`/api/order/${viewer.threadId}`}
          editable
          onKindChange={(id, kind) => setViewer((v: any) => v && ({ ...v, images: v.images.map((x: any) => (x.id === id ? { ...x, kind } : x)) }))}
          onClose={() => setViewer(null)}
        />
      )}
    </div>
  );
}
