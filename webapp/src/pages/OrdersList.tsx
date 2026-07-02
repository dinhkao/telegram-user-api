// Danh sách đơn — search (FTS server), lọc xong/chưa, phân trang "Tải thêm".
// Data: GET /api/orders (server_app/orders_api.py). Card → #/order/:thread_id.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money } from "../format";
import { onRealtime } from "../realtime";

type OrderRow = {
  thread_id: number;
  customer: string;
  total: string;
  paid: number;
  remaining: number;
  date: string;
  hd_code: string;
  soan: boolean;
  giao: boolean;
  nop: boolean;
  nhan: boolean;
  done_after_20250124: boolean;
  invoice_count: number;
  topic_name: string;
  creator: string;
  text: string;
};

// Cache toàn danh sách + vị trí cuộn — sống ở module scope nên vẫn còn khi
// rời trang chi tiết rồi quay lại (mount lại). Reset khi có search mới.
let listCache: {
  orders: OrderRow[]; stats: any; search: string;
  filter: "all" | "pending" | "done"; page: number; totalPages: number; scrollY: number;
} | null = null;

function TaskBadges({ o }: { o: OrderRow }) {
  const items: [string, boolean][] = [["Soạn", o.soan], ["Giao", o.giao], ["Nộp", o.nop], ["Nhận", o.nhan]];
  return (
    <span class="badges">
      {items.map(([label, done]) => (
        <span class={done ? "badge done" : "badge"}>{label}</span>
      ))}
    </span>
  );
}

export function OrdersList() {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "pending" | "done">("all");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [stale, setStale] = useState(false);
  const [err, setErr] = useState("");
  const debounce = useRef<number>();
  const sentinel = useRef<HTMLDivElement>(null);
  // refs giữ state mới nhất cho observer (tránh stale closure)
  const st = useRef<any>({});
  st.current = { page, totalPages, loading, search, filter, orders, stats };

  const PAGE_SIZE = 20; // luôn tải 20 mỗi lần, kể cả lần đầu — không bao giờ tải hết

  const load = async (p: number, q: string, f: string, append: boolean) => {
    setLoading(true);
    setErr("");
    try {
      // filter=all → không gửi (server mặc định all). Lọc pending/done server-side.
      const fp = f && f !== "all" ? `&filter=${f}` : "";
      // chỉ cache trang không search — kết quả theo phím gõ không rác localStorage
      const data = await getJSON(`/api/orders?page=${p}&limit=${PAGE_SIZE}&search=${encodeURIComponent(q)}${fp}`, { cache: !q });
      setOrders((prev) => (append ? [...prev, ...data.orders] : data.orders));
      setTotalPages(data.total_pages || 1);
      if (data.stats && Object.keys(data.stats).length) setStats(data.stats);
      setStale(!!data._stale);
    } catch (ex: any) {
      setErr(ex.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
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
      // Quay lại từ trang chi tiết → khôi phục danh sách + vị trí cuộn, không fetch lại
      const c = listCache;
      setOrders(c.orders);
      setStats(c.stats);
      setSearch(c.search);
      setFilter(c.filter);
      setPage(c.page);
      setTotalPages(c.totalPages);
      // đợi 2 frame cho danh sách render đủ chiều cao rồi mới cuộn
      requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo(0, c.scrollY)));
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
        orders: s.orders, stats: s.stats, search: s.search, filter: s.filter,
        page: s.page, totalPages: s.totalPages, scrollY: window.scrollY,
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
      setOrders((prev) => {
        const idx = prev.findIndex((o) => String(o.thread_id) === tid);
        let next = prev;
        if (e.row === null) {
          if (idx < 0) return prev;
          next = prev.filter((_, i) => i !== idx); // đơn bị xoá
        } else if (idx >= 0) {
          next = prev.slice();
          next[idx] = e.row as OrderRow; // vá dòng đã đổi
        } else {
          return prev; // chưa có trong danh sách hiện tại → hiện ở lần tải sau
        }
        if (listCache) listCache = { ...listCache, orders: next }; // đồng bộ cache module
        return next;
      });
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

  const onSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => load(1, q, st.current.filter, false), 350);
  };

  // Đổi chip → reset trang, tải lại từ server với filter mới (nhất quán phân trang)
  const onFilter = (f: "all" | "pending" | "done") => {
    setFilter(f);
    setPage(1);
    load(1, search, f, false);
  };

  const visible = orders;

  return (
    <div>
      <header class="topbar">
        <input
          class="search"
          type="search"
          placeholder="🔍 Tìm khách, mã HĐ, sản phẩm…"
          value={search}
          onInput={(e: any) => onSearch(e.target.value)}
        />
      </header>
      {stats && (
        <div class="chips">
          <button class={filter === "all" ? "chip active" : "chip"} onClick={() => onFilter("all")}>Tất cả {stats.total_orders}</button>
          <button class={filter === "pending" ? "chip active" : "chip"} onClick={() => onFilter("pending")}>Chưa xong {stats.pending}</button>
          <button class={filter === "done" ? "chip active" : "chip"} onClick={() => onFilter("done")}>Xong {stats.done}</button>
        </div>
      )}
      {stale && <p class="muted small">⚠️ Dữ liệu lưu sẵn (mất mạng)</p>}
      {err && <p class="error">{err}</p>}
      <ul class="order-list">
        {visible.map((o) => (
          <li key={o.thread_id}>
            <a class="order-card" href={`#/order/${o.thread_id}`}>
              {o.text
                ? <div class="order-text">{o.text}</div>
                : <div class="order-text muted">(không có nội dung)</div>}
              <div class="row space">
                <b class="cust">{o.customer || o.topic_name || `#${o.thread_id}`}</b>
                <span class="muted small">{o.date}</span>
              </div>
              <div class="row space">
                <span>
                  {o.total && <b class="money">{o.total}đ</b>}
                  {o.remaining > 0 && <span class="owe"> · thiếu {money(o.remaining)}đ</span>}
                </span>
                <TaskBadges o={o} />
              </div>
              <div class="muted small">
                {o.hd_code && <span>{o.hd_code} · </span>}
                {o.invoice_count} món{o.creator ? ` · ${o.creator}` : ""}
              </div>
            </a>
          </li>
        ))}
      </ul>
      {loading && <p class="muted center">Đang tải…</p>}
      {/* sentinel cho infinite scroll — observer tải trang kế khi lọt khung nhìn */}
      <div ref={sentinel} style="height:1px" />
      {!loading && page >= totalPages && visible.length > 0 && (
        <p class="muted center small">— Hết đơn —</p>
      )}
      {!loading && !visible.length && !err && <p class="muted center">Không có đơn nào</p>}
    </div>
  );
}
