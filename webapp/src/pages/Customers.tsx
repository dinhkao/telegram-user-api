// Khách hàng — tìm kiếm + công nợ + infinite scroll. GET /api/customers?search=&sort=recent&page=.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money, fmtTime } from "../format";
import { onRealtime } from "../realtime";
import { Loading, EmptyState } from "../ui/states";

const PAGE_SIZE = 30;

// Cache toàn bộ list đã tải (module scope) → quay lại giữ nguyên list + vị trí cuộn
// (hệ cuộn trung tâm main.tsx khôi phục ngay, khỏi refetch/nhảy trang).
let custCache: { customers: any[]; page: number; totalPages: number; search: string } | null = null;

export function Customers() {
  const [search, setSearch] = useState("");
  const [customers, setCustomers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const reqSeq = useRef(0);
  const sentinel = useRef<HTMLDivElement>(null);
  const st = useRef({ page: 1, totalPages: 1, loading: false, search: "" });
  st.current = { page, totalPages, loading, search };
  const snap = useRef<any>(null);
  snap.current = { customers, page, totalPages, search };

  const load = async (p: number, q: string, append: boolean) => {
    const seq = ++reqSeq.current;
    setLoading(true);
    setErr("");
    try {
      const r = await getJSON(
        `/api/customers?search=${encodeURIComponent(q)}&limit=${PAGE_SIZE}&page=${p}&sort=recent`,
        { cache: false },
      );
      if (seq !== reqSeq.current) return;
      setTotalPages(r.total_pages || 1);
      setCustomers((prev) => (append ? [...prev, ...(r.customers || [])] : r.customers || []));
    } catch (ex: any) {
      if (seq === reqSeq.current) setErr(ex.message);
    } finally {
      if (seq === reqSeq.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (custCache) {   // quay lại → dựng lại list đã tải (đủ cao cho hệ cuộn khôi phục)
      setCustomers(custCache.customers);
      setPage(custCache.page);
      setTotalPages(custCache.totalPages);
      setSearch(custCache.search);
      return;
    }
    load(1, "", false);
  }, []);
  // Lưu snapshot khi rời trang
  useEffect(() => () => { if (snap.current?.customers?.length) custCache = { ...snap.current }; }, []);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) return;
        const { page: p, totalPages: tp, loading: ld, search: q } = st.current;
        if (ld || p >= tp) return;
        const next = p + 1;
        setPage(next);
        load(next, q, true);
      },
      { rootMargin: "300px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Realtime: cập nhật công nợ/khách MÀ KHÔNG co danh sách về trang 1. Lấy trang 1 mới
  // rồi VÁ tại chỗ theo key (giữ nguyên các trang đã cuộn + vị trí), chèn khách mới lên đầu.
  const refreshMerge = async () => {
    try {
      const q = st.current.search;
      const r = await getJSON(`/api/customers?search=${encodeURIComponent(q)}&limit=${PAGE_SIZE}&page=1&sort=recent`, { cache: false });
      const fresh: any[] = r.customers || [];
      const byKey = new Map(fresh.map((c) => [c.key, c]));
      setCustomers((prev) => {
        const seen = new Set(prev.map((c) => c.key));
        const patched = prev.map((c) => byKey.get(c.key) || c);          // cập nhật tại chỗ
        const added = fresh.filter((c) => !seen.has(c.key));             // khách mới → lên đầu
        return added.length ? [...added, ...patched] : patched;
      });
    } catch { /* im lặng */ }
  };
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "order_changed" || e.type === "orders_changed" || e.type === "customer_changed") {
        clearTimeout(t);
        t = setTimeout(refreshMerge, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  const onSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    if (q.length === 1) return;
    load(1, q, false);
  };

  return (
    <div>
      <header class="topbar">
        <input
          class="search"
          type="search"
          placeholder="🔍 Tìm khách hàng…"
          value={search}
          onInput={(e: any) => onSearch(e.target.value)}
        />
      </header>
      {err && <p class="error">{err}</p>}
      <ul class="order-list">
        {customers.map((c) => (
          <li key={c.key}>
            <a class="order-card" href={`#/khach/${encodeURIComponent(c.key)}`}>
              <div class="row space">
                <b>{c.name}</b>
                {c.debt != null && (
                  <span class={Number(c.debt) > 0 ? "owe" : "muted"}>
                    nợ {money(Number(c.debt) || 0)}đ
                  </span>
                )}
              </div>
              <div class="row space">
                <span class="muted small">
                  {c.kh_id ? `KV: ${c.kh_id} · ` : ""}
                  {c.key}
                </span>
                {c.last_order_at && <span class="muted small">📦 {fmtTime(c.last_order_at)}</span>}
              </div>
              <span class="muted small">✏️ Sửa bảng giá · pattern · xem đơn →</span>
            </a>
          </li>
        ))}
      </ul>
      <div ref={sentinel} style="height:1px" />
      {loading && <Loading />}
      {!loading && !customers.length && !err && <EmptyState>Không thấy khách</EmptyState>}
      {!loading && page >= totalPages && customers.length > 0 && (
        <p class="muted center small">Hết danh sách ({customers.length} khách)</p>
      )}
    </div>
  );
}
