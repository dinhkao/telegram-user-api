// Khách hàng — tìm kiếm + công nợ + infinite scroll. GET /api/customers?search=&sort=recent&page=.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money, fmtTime } from "../format";
import { onRealtime } from "../realtime";

const PAGE_SIZE = 30;

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
    load(1, "", false);
  }, []);

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

  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "order_changed" || e.type === "orders_changed") {
        clearTimeout(t);
        t = setTimeout(() => load(1, st.current.search, false), 300);
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
      {loading && <p class="muted center">Đang tải…</p>}
      {!loading && !customers.length && !err && <p class="muted center">Không thấy khách</p>}
      {!loading && page >= totalPages && customers.length > 0 && (
        <p class="muted center small">Hết danh sách ({customers.length} khách)</p>
      )}
    </div>
  );
}
