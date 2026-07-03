// Danh sách đơn — search (FTS server), lọc xong/chưa, phân trang "Tải thêm".
// Data: GET /api/orders (server_app/orders_api.py). Card → #/order/:thread_id.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money, fmtDateTimeVN, fmtRelative } from "../format";
import { onRealtime } from "../realtime";
import { InvoiceTable } from "../detail/InvoiceTable";
import { orderImageUrl } from "../api";

type OrderRow = {
  thread_id: number;
  thumb_image_id?: number | null;
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
  invoice_summary?: { sp: string; sl: number | string }[];
  invoice_items?: { sp: string; sl: number | string; price: number }[];
  vat?: number;
  pvc?: number;
  discount?: number;
  no_truoc?: string;
  kh_debt?: number | null;
  created?: string;
  giao_by?: string;
  nop_by?: string;
  nop_note?: string;
  task_icons?: string;
  topic_name: string;
  creator: string;
  text: string;
};

// Mã ghi chú nộp tiền → tiếng Việt đầy đủ
const NOP_NOTE_VI: Record<string, string> = {
  co_ky_toa: "có ký toa",
  khong_ky_toa: "không ký toa",
  tra_tien_mat: "trả tiền mặt",
  chieu_lay_tien: "chiều lấy tiền",
};
const noteVi = (n?: string) => NOP_NOTE_VI[(n || "").toLowerCase()] || (n || "").replace(/_/g, " ").trim();

// Nhãn trạng thái workflow (thay cho "thiếu <số tiền>")
function statusLabel(o: OrderRow): string {
  if (!o.soan) return "Chưa soạn";
  if (!o.giao) return "Chưa giao";
  if (!o.nop) {
    // "chiều lấy tiền": đã giao, hẹn thu sau (chưa nộp) → hiện rõ lý do
    if ((o.nop_note || "").toLowerCase() === "chieu_lay_tien") {
      const who = o.nop_by || o.giao_by;
      return `${who ? `${who} ` : ""}chiều lấy tiền`;
    }
    return o.giao_by ? `${o.giao_by} chưa nộp` : "Chưa nộp";
  }
  const note = noteVi(o.nop_note);
  return `${o.nop_by ? `${o.nop_by} ` : ""}đã nộp${note ? ` (${note})` : ""}`;
}

// Tô sáng cụm khớp khi tìm kiếm (không phân biệt hoa/thường)
function Highlight({ text, q }: { text: string; q: string }) {
  const s = (text || "").trim();
  const query = (q || "").trim();
  if (!query || !s) return <>{s}</>;
  const re = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig");
  const parts = s.split(re);
  return <>{parts.map((p, i) => (i % 2 === 1 ? <mark key={i}>{p}</mark> : p))}</>;
}

// Bảng chi tiết hoá đơn 1 đơn (dùng ở card dashboard) — dùng chung InvoiceTable
function InvoiceMini({ o, q }: { o: OrderRow; q?: string }) {
  if (!(o.invoice_items || []).length) return null;
  return <InvoiceTable items={o.invoice_items || []} discount={o.discount} pvc={o.pvc} vat={o.vat} debt={o.kh_debt} total={o.total} q={q} />;
}

type FilterKey = "all" | "pending" | "done" | "chua_soan" | "chua_giao" | "chua_nop" | "chua_nhan";

// Cache toàn danh sách + vị trí cuộn — sống ở module scope nên vẫn còn khi
// rời trang chi tiết rồi quay lại (mount lại). Reset khi có search mới.
let listCache: {
  orders: OrderRow[]; stats: any; search: string;
  filter: FilterKey; page: number; totalPages: number; scrollY: number;
} | null = null;

/** No-op giữ lại cho tương thích: giờ dashboard LUÔN refetch trang 1 khi remount
 *  (giữ nguyên search/filter/scroll từ cache), nên không cần xoá cache sau mutation
 *  — làm vậy sẽ mất filter đang chọn. Freshness do refetch lo. */
export function invalidateListCache() {
  /* no-op */
}

// Đơn cuối cùng người dùng mở — để tô sáng trên dashboard khi quay lại.
export function markLastOrder(id: string | number) {
  try { localStorage.setItem("last_order", String(id)); } catch { /* ignore */ }
}
function getLastOrder(): string {
  try { return localStorage.getItem("last_order") || ""; } catch { return ""; }
}

// 5 task icon y hệt main message Telegram: HĐ · Soạn · Giao · Nộp · Nhận
const TASK_LABELS = ["HĐ", "Soạn", "Giao", "Nộp", "Nhận"];
function TaskBadges({ o }: { o: OrderRow }) {
  const icons = [...(o.task_icons || "")];
  const fallback: boolean[] = [false, o.soan, o.giao, o.nop, o.nhan];
  return (
    <span class="badges">
      {TASK_LABELS.map((label, i) => (
        <span class="tstat" key={label}>
          <span class="tico">{icons[i] || (fallback[i] ? "✅" : "❌")}</span>
          <span class="tlbl">{label}</span>
        </span>
      ))}
    </span>
  );
}

export function OrdersList() {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [stale, setStale] = useState(false);
  const [err, setErr] = useState("");
  const [compact, setCompact] = useState(() => localStorage.getItem("dash_compact") === "1");
  const toggleCompact = () => setCompact((c) => { localStorage.setItem("dash_compact", c ? "0" : "1"); return !c; });
  const [flashing, setFlashing] = useState<Record<string, string>>({});
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
  st.current = { page, totalPages, loading, search, filter, orders, stats };

  const PAGE_SIZE = 20; // luôn tải 20 mỗi lần, kể cả lần đầu — không bao giờ tải hết

  const load = async (p: number, q: string, f: string, append: boolean) => {
    const seq = ++reqSeq.current; // đánh dấu request này là mới nhất
    setLoading(true);
    setErr("");
    try {
      // filter=all → không gửi (server mặc định all). Lọc pending/done server-side.
      const fp = f && f !== "all" ? `&filter=${f}` : "";
      // chỉ cache trang không search — kết quả theo phím gõ không rác localStorage
      const data = await getJSON(`/api/orders?page=${p}&limit=${PAGE_SIZE}&search=${encodeURIComponent(q)}${fp}`, { cache: !q });
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
      // Quay lại → vẽ ngay từ cache (mượt + giữ vị trí cuộn) NHƯNG luôn refetch nền
      // để có DATA MỚI NHẤT (thay đổi lúc rời trang mà realtime chưa bắt được).
      const c = listCache;
      setOrders(c.orders);
      setStats(c.stats);
      setSearch(c.search);
      setFilter(c.filter);
      setPage(1);
      setTotalPages(c.totalPages);
      requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo(0, c.scrollY)));
      load(1, c.search, c.filter, false); // làm mới trang 1 theo search/filter cũ
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
      let patched = false;
      setOrders((prev) => {
        const idx = prev.findIndex((o) => String(o.thread_id) === tid);
        let next = prev;
        if (e.row === null) {
          if (idx < 0) return prev;
          next = prev.filter((_, i) => i !== idx); // đơn bị xoá
        } else if (idx >= 0) {
          next = prev.slice();
          next[idx] = e.row as OrderRow; // vá dòng đã đổi
          patched = true;
        } else {
          return prev; // chưa có trong danh sách hiện tại → hiện ở lần tải sau
        }
        if (listCache) listCache = { ...listCache, orders: next }; // đồng bộ cache module
        return next;
      });
      if (patched) flashOrder(tid); // nháy sáng + hiện thao tác vừa xảy ra
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
    load(1, q, st.current.filter, false); // gõ tới đâu tìm tới đó — không delay (reqSeq chặn race)
  };

  // Đổi chip → reset trang, tải lại từ server với filter mới (nhất quán phân trang)
  const onFilter = (f: FilterKey) => {
    setFilter(f);
    setPage(1);
    load(1, search, f, false);
  };

  // Đang lọc? (có search hoặc chip khác "tất cả") → cho phép bỏ lọc về mặc định
  const anyFilter = search.trim() !== "" || filter !== "all";
  const clearFilters = () => {
    setSearch("");
    setFilter("all");
    setPage(1);
    load(1, "", "all", false);
  };

  const visible = orders;
  const lastOrder = getLastOrder(); // đơn vừa mở → tô sáng khi quay lại dashboard

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
        {anyFilter && <button class="btn small clear-filter" onClick={clearFilters}>✕ Bỏ lọc</button>}
        <button class="btn small clear-filter" title="Đổi kiểu xem" onClick={toggleCompact}>{compact ? "⊞" : "⊟"}</button>
      </header>
      {stats && (
        <div class="chips">
          <button class={filter === "all" ? "chip active" : "chip"} onClick={() => onFilter("all")}>Tất cả {stats.total_orders}</button>
          <button class={filter === "pending" ? "chip active" : "chip"} onClick={() => onFilter("pending")}>Chưa xong {stats.pending}</button>
          <button class={filter === "done" ? "chip active" : "chip"} onClick={() => onFilter("done")}>Xong {stats.done}</button>
          <button class={filter === "chua_soan" ? "chip active" : "chip"} onClick={() => onFilter("chua_soan")}>Chưa soạn {stats.chua_soan ?? ""}</button>
          <button class={filter === "chua_giao" ? "chip active" : "chip"} onClick={() => onFilter("chua_giao")}>Chưa giao {stats.chua_giao ?? ""}</button>
          <button class={filter === "chua_nop" ? "chip active" : "chip"} onClick={() => onFilter("chua_nop")}>Chưa nộp {stats.chua_nop ?? ""}</button>
          <button class={filter === "chua_nhan" ? "chip active" : "chip"} onClick={() => onFilter("chua_nhan")}>Chưa nhận {stats.chua_nhan ?? ""}</button>
        </div>
      )}
      {stale && <p class="muted small">⚠️ Dữ liệu lưu sẵn (mất mạng)</p>}
      {err && <p class="error">{err}</p>}
      <ul class="order-list">
        {compact && visible.map((o) => (
          <li key={o.thread_id}>
            <a class={`order-card compact${flashing[String(o.thread_id)] ? " flash" : ""}${String(o.thread_id) === lastOrder ? " last-visited" : ""}`} href={`#/order/${o.thread_id}`}>
              {flashing[String(o.thread_id)] && <div class="flash-msg">🔔 {flashing[String(o.thread_id)]}</div>}
              {o.thumb_image_id ? <img class="card-thumb" src={orderImageUrl(o.thread_id, o.thumb_image_id, "thumb")} loading="lazy" alt="" /> : null}
              <div class="order-text">
                <span class="ot-text">
                  {o.text ? <Highlight text={o.text} q={search} /> : <span class="muted">(không có nội dung)</span>}
                </span>
                <TaskBadges o={o} />
              </div>
            </a>
          </li>
        ))}
        {!compact && visible.map((o) => {
          const stt = statusLabel(o);
          return (
          <li key={o.thread_id}>
            <a class={`order-card two-col${flashing[String(o.thread_id)] ? " flash" : ""}${String(o.thread_id) === lastOrder ? " last-visited" : ""}`} href={`#/order/${o.thread_id}`}>
              <div class="card-main">
                {flashing[String(o.thread_id)] && <div class="flash-msg">🔔 {flashing[String(o.thread_id)]}</div>}
                <div class="card-lead">
                  {o.thumb_image_id ? <img class="card-thumb" src={orderImageUrl(o.thread_id, o.thumb_image_id, "thumb")} loading="lazy" alt="" /> : null}
                  {o.text
                    ? <div class="order-text"><span class="ot-text"><Highlight text={o.text} q={search} /></span><TaskBadges o={o} /></div>
                    : <div class="order-text muted"><span class="ot-text">(không có nội dung)</span><TaskBadges o={o} /></div>}
                </div>
                <div class="row space">
                  <b class="cust"><Highlight text={o.customer || o.topic_name || `#${o.thread_id}`} q={search} /></b>
                  <span class="muted small order-when">
                    {o.created ? (
                      <>🕒 {fmtDateTimeVN(o.created)} · {fmtRelative(o.created)}</>
                    ) : (
                      o.date
                    )}
                  </span>
                </div>
                <div class="row space">
                  <span>
                    {o.total && <b class="money">{o.total}đ</b>}
                    {stt && <span class={stt.includes("đã nộp") ? "paid-ok" : "owe"}> · {stt}</span>}
                  </span>
                </div>
                <div class="muted small">
                  {o.hd_code && <span>{o.hd_code} · </span>}
                  {o.invoice_count} món{o.creator ? ` · ${o.creator}` : ""}
                </div>
              </div>
              <div class="card-inv"><InvoiceMini o={o} q={search} /></div>
            </a>
          </li>
          );
        })}
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
