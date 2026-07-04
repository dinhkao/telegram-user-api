// Danh sách đơn — search (FTS server), lọc xong/chưa, phân trang "Tải thêm".
// Data: GET /api/orders (server_app/orders_api.py). Card → #/order/:thread_id.
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money, fmtDateTimeVN, fmtRelative, fmtNgayGiao, foldVN, isRecent } from "../format";

const NEW_ORDER_SEC = 5 * 60; // đơn tạo trong 5 phút → tô vàng + tag "Mới"
import { onRealtime } from "../realtime";
import { InvoiceTable } from "../detail/InvoiceTable";
import { orderImageUrl, listOrderImages, type OrderImage } from "../api";
import { PhotoViewer } from "../detail/PhotoViewer";
import { Loading, EmptyState } from "../ui/states";

type OrderRow = {
  thread_id: number;
  thumb_image_id?: number | null;
  thumb_image_ids?: number[];
  image_count?: number;
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
  ngay_giao?: string;
  giao_by?: string;
  nop_by?: string;
  nop_note?: string;
  task_icons?: string;
  topic_name: string;
  creator: string;
  text: string;
  last_action?: string | null; // view 'Mới cập nhật': thao tác mới nhất (giàu như Lịch sử)
  last_detail?: string | null;
  last_changes?: { label: string; old: string; new: string }[];
  last_actor?: string | null;
  last_action_ts?: string | null;
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
  // So khớp KHÔNG DẤU: fold cả text + query (giữ độ dài) rồi map vị trí về text gốc.
  const fs = foldVN(s);
  const fq = foldVN(query);
  if (!fq) return <>{s}</>;
  const parts: any[] = [];
  let from = 0, idx: number, key = 0;
  while ((idx = fs.indexOf(fq, from)) !== -1) {
    if (idx > from) parts.push(s.slice(from, idx));
    parts.push(<mark key={key++}>{s.slice(idx, idx + fq.length)}</mark>);
    from = idx + fq.length;
  }
  parts.push(s.slice(from));
  return <>{parts}</>;
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

/** Bấm tab Đơn → về đầu danh sách: xoá scrollY đã nhớ (để khi vào lại không khôi
 *  phục vị trí cũ) + cuộn cửa sổ lên đầu ngay nếu đang ở trang Đơn. */
export function resetOrdersScroll() {
  if (listCache) listCache.scrollY = 0;
  window.scrollTo({ top: 0, behavior: "smooth" });
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
// Dòng "thao tác mới nhất" trên card (view Mới cập nhật) — giàu như Lịch sử thao tác
function LastAction({ o }: { o: OrderRow }) {
  if (!o.last_action) return null;
  const ch = Array.isArray(o.last_changes) ? o.last_changes : [];
  return (
    <div class="last-act">
      <div class="la-head">⚡ <b>{o.last_action}</b>{o.last_detail ? <span> — {o.last_detail}</span> : null}</div>
      {ch.length > 0 && (
        <ul class="la-changes">
          {ch.slice(0, 4).map((c, ci) => (
            <li key={ci}>
              <span class="hc-label">{c.label}:</span>{" "}
              {c.old ? <span class="hc-old">{c.old}</span> : null}
              {c.old && c.new ? <span class="hc-arrow"> → </span> : null}
              {c.new ? <span class="hc-new">{c.new}</span> : null}
            </li>
          ))}
          {ch.length > 4 && <li class="muted">+{ch.length - 4} thay đổi nữa</li>}
        </ul>
      )}
      <div class="la-meta">{o.last_actor || "?"} · {fmtRelative(o.last_action_ts)}</div>
    </div>
  );
}

// Thân card two-col: cột thumbnail (trái) + nội dung (phải). ĐO chiều cao nội dung
// thật (ResizeObserver) → nếu đủ cho 2 ô vuông (H ≥ 2×rộng-cột + gap) thì hiện 2 ảnh.
function CardBody({ o, search, stt, isNew, openThumb, filterByCustomer }: {
  o: OrderRow; search: string; stt: string; isNew: boolean;
  openThumb: (e: Event, o: OrderRow, atId?: number) => void;
  filterByCustomer: (e: Event, c: string) => void;
}) {
  const allIds = o.thumb_image_ids && o.thumb_image_ids.length ? o.thumb_image_ids : (o.thumb_image_id ? [o.thumb_image_id] : []);
  const total = o.image_count ?? allIds.length;
  const contentRef = useRef<HTMLDivElement>(null);
  const colRef = useRef<HTMLDivElement>(null);
  const [two, setTwo] = useState(false);
  useLayoutEffect(() => {
    if (allIds.length < 2) { setTwo(false); return; }
    const el = contentRef.current;
    if (!el) return;
    const measure = () => {
      const h = el.offsetHeight; // chiều cao nội dung TỰ NHIÊN (không bị flex kéo giãn)
      const w = colRef.current?.offsetWidth || 100;
      setTwo(h >= 2 * w + 6); // 2 ô vuông xếp dọc + gap 6px
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    if (colRef.current) ro.observe(colRef.current);
    return () => ro.disconnect();
  }, [allIds.length, o.text, o.last_action, o.last_changes?.length, o.customer, o.total]);
  const shown = two ? allIds.slice(0, 2) : allIds.slice(0, 1);
  return (
    <div class="card-body">
      {allIds.length > 0 && (
        <div class="card-thumb-col" ref={colRef}>
          {shown.map((id, i) => (
            <span class="card-thumb-wrap" key={id} onClick={(e) => openThumb(e, o, id)}>
              <img class="card-thumb card-thumb-tile" src={orderImageUrl(o.thread_id, id, "thumb")} loading="lazy" alt="" />
              {i === shown.length - 1 && total > shown.length && <span class="thumb-count">+{total - shown.length}</span>}
            </span>
          ))}
        </div>
      )}
      <div class="card-content">
        <div class="cc-measure" ref={contentRef}>
          {o.text
            ? <div class="order-text wrap-badges"><TaskBadges o={o} />{o.ngay_giao && <span class="od-deliver">🚚 {fmtNgayGiao(o.ngay_giao)}</span>}<span class="ot-text"><Highlight text={o.text} q={search} /></span></div>
            : <div class="order-text muted wrap-badges"><TaskBadges o={o} />{o.ngay_giao && <span class="od-deliver">🚚 {fmtNgayGiao(o.ngay_giao)}</span>}<span class="ot-text">(không có nội dung)</span></div>}
          <div class="row space">
            <b class="cust">{isNew && <span class="tag-new">Mới</span>} <Highlight text={o.customer || o.topic_name || `#${o.thread_id}`} q={search} />
              {o.customer ? <button class="cust-filter" title={`Lọc đơn của ${o.customer}`} onClick={(e) => filterByCustomer(e, o.customer)}>🔎</button> : null}</b>
            <span class="muted small order-when">
              {o.created ? <>🕒 {fmtDateTimeVN(o.created)} · {fmtRelative(o.created)}</> : o.date}
            </span>
          </div>
          <div class="row space">
            <span>
              {o.total && <b class="money">{o.total}đ</b>}
              {stt && <span class={stt.includes("đã nộp") ? "paid-ok" : "owe"}> · {stt}</span>}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// Thân card COMPACT: cột thumbnail (trái) + nội dung (phải). Đo chiều cao nội dung
// thật → đủ cho 2 ô vuông thì hiện 2 (giống card two-col, tile hẹp hơn ~68px).
function CompactBody({ o, search, sort, flashMsg, isNew, openThumb }: {
  o: OrderRow; search: string; sort: string; flashMsg?: string; isNew: boolean;
  openThumb: (e: Event, o: OrderRow, atId?: number) => void;
}) {
  const allIds = o.thumb_image_ids && o.thumb_image_ids.length ? o.thumb_image_ids : (o.thumb_image_id ? [o.thumb_image_id] : []);
  const total = o.image_count ?? allIds.length;
  const contentRef = useRef<HTMLDivElement>(null);
  const colRef = useRef<HTMLDivElement>(null);
  const [two, setTwo] = useState(false);
  useLayoutEffect(() => {
    if (allIds.length < 2) { setTwo(false); return; }
    const el = contentRef.current;
    if (!el) return;
    const measure = () => {
      const w = colRef.current?.offsetWidth || 68;
      setTwo(el.offsetHeight >= 2 * w + 4);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    if (colRef.current) ro.observe(colRef.current);
    return () => ro.disconnect();
  }, [allIds.length, o.text, o.last_action, o.last_changes?.length, sort, flashMsg]);
  const shown = two ? allIds.slice(0, 2) : allIds.slice(0, 1);
  return (
    <>
      {allIds.length > 0 && (
        <div class="compact-thumb-col" ref={colRef}>
          {shown.map((id, i) => (
            <span class="card-thumb-wrap" key={id} onClick={(e) => openThumb(e, o, id)}>
              <img class="card-thumb card-thumb-tile" src={orderImageUrl(o.thread_id, id, "thumb")} loading="lazy" alt="" />
              {i === shown.length - 1 && total > shown.length && <span class="thumb-count">+{total - shown.length}</span>}
            </span>
          ))}
        </div>
      )}
      <div class="compact-right">
        <div class="cc-measure" ref={contentRef}>
          {sort === "updated" && <LastAction o={o} />}
          {flashMsg && <div class="flash-msg">🔔 {flashMsg}</div>}
          <div class="order-text wrap-badges">
            <TaskBadges o={o} />
            {o.ngay_giao && <span class="od-deliver">🚚 {fmtNgayGiao(o.ngay_giao)}</span>}
            <span class="ot-text">
              {isNew && <span class="tag-new">Mới</span>}
              {o.text ? <Highlight text={o.text} q={search} /> : <span class="muted">(không có nội dung)</span>}
            </span>
          </div>
          <div class="order-when muted small">
            🕒 {o.created ? <>{fmtDateTimeVN(o.created)} · {fmtRelative(o.created)}</> : o.date}
          </div>
        </div>
      </div>
    </>
  );
}

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
  const [sort, setSort] = useState<"created" | "updated">(() => (localStorage.getItem("dash_sort") === "updated" ? "updated" : "created"));
  const sortRef = useRef(sort); // đọc trong load (tránh stale closure)
  const changeSort = (s: "created" | "updated") => {
    if (s === sortRef.current) return;
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
  st.current = { page, totalPages, loading, search, filter, orders, stats };

  const PAGE_SIZE = 20; // luôn tải 20 mỗi lần, kể cả lần đầu — không bao giờ tải hết

  const load = async (p: number, q: string, f: string, append: boolean) => {
    const seq = ++reqSeq.current; // đánh dấu request này là mới nhất
    setLoading(true);
    setErr("");
    try {
      // filter=all → không gửi (server mặc định all). Lọc pending/done server-side.
      const fp = f && f !== "all" ? `&filter=${f}` : "";
      const sp = sortRef.current === "updated" ? "&sort=updated" : "";
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
  // Nhịp 60s để tag "Mới" tự hết sau 5 phút (không cần event khác)
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 60000);
    return () => clearInterval(id);
  }, []);

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
          <button class={filter === "all" ? "chip active" : "chip"} onClick={() => onFilter("all")}>Tất cả</button>
          <button class={filter === "chua_soan" ? "chip active" : "chip"} onClick={() => onFilter("chua_soan")}>Chưa soạn {stats.chua_soan != null ? `(${stats.chua_soan})` : ""}</button>
          <button class={filter === "chua_giao" ? "chip active" : "chip"} onClick={() => onFilter("chua_giao")}>Chưa giao {stats.chua_giao != null ? `(${stats.chua_giao})` : ""}</button>
          <button class={filter === "chua_nop" ? "chip active" : "chip"} onClick={() => onFilter("chua_nop")}>Chưa nộp {stats.chua_nop != null ? `(${stats.chua_nop})` : ""}</button>
          <button class={filter === "chua_nhan" ? "chip active" : "chip"} onClick={() => onFilter("chua_nhan")}>Chưa nhận {stats.chua_nhan != null ? `(${stats.chua_nhan})` : ""}</button>
        </div>
      )}
      <div class="sort-row">
        <span class="sort-lbl">Sắp xếp:</span>
        <button class={sort === "created" ? "sort-opt active" : "sort-opt"} onClick={() => changeSort("created")}>Mới tạo</button>
        <button class={sort === "updated" ? "sort-opt active" : "sort-opt"} onClick={() => changeSort("updated")}>Mới cập nhật</button>
        <a class="sort-opt cal-chip" href="#/lich" title="Lịch giao hàng">📅 Lịch giao</a>
      </div>
      {stale && <p class="muted small">⚠️ Dữ liệu lưu sẵn (mất mạng)</p>}
      {err && <p class="error">{err}</p>}
      <ul class="order-list">
        {compact && visible.map((o) => {
          const isNew = isRecent(o.created, NEW_ORDER_SEC);
          return (
          <li key={o.thread_id}>
            <a class={`order-card compact${flashing[String(o.thread_id)] ? " flash" : ""}${String(o.thread_id) === lastOrder ? " last-visited" : ""}${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
              <CompactBody o={o} search={search} sort={sort} flashMsg={flashing[String(o.thread_id)]} isNew={isNew} openThumb={openThumb} />
            </a>
          </li>
          );
        })}
        {!compact && visible.map((o) => {
          const stt = statusLabel(o);
          const isNew = isRecent(o.created, NEW_ORDER_SEC);
          return (
          <li key={o.thread_id}>
            <a class={`order-card two-col${flashing[String(o.thread_id)] ? " flash" : ""}${String(o.thread_id) === lastOrder ? " last-visited" : ""}${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
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
      {loading && <Loading />}
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
          threadId={viewer.threadId}
          onClose={() => setViewer(null)}
        />
      )}
    </div>
  );
}
