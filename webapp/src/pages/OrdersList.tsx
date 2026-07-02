// Danh sách đơn — search (FTS server), lọc xong/chưa, phân trang "Tải thêm".
// Data: GET /api/orders (server_app/orders_api.py). Card → #/order/:thread_id.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money } from "../format";

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
};

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

  const load = async (p: number, q: string, append: boolean) => {
    setLoading(true);
    setErr("");
    try {
      const data = await getJSON(`/api/orders?page=${p}&limit=30&search=${encodeURIComponent(q)}`);
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
      setSearch(pending);
    }
    load(1, pending, false);
  }, []);

  const onSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => load(1, q, false), 350);
  };

  const visible = orders.filter((o) =>
    filter === "all" ? true : filter === "done" ? o.done_after_20250124 : !o.done_after_20250124
  );

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
          <button class={filter === "all" ? "chip active" : "chip"} onClick={() => setFilter("all")}>Tất cả {stats.total_orders}</button>
          <button class={filter === "pending" ? "chip active" : "chip"} onClick={() => setFilter("pending")}>Chưa xong {stats.pending}</button>
          <button class={filter === "done" ? "chip active" : "chip"} onClick={() => setFilter("done")}>Xong {stats.done}</button>
        </div>
      )}
      {stale && <p class="muted small">⚠️ Dữ liệu lưu sẵn (mất mạng)</p>}
      {err && <p class="error">{err}</p>}
      <ul class="order-list">
        {visible.map((o) => (
          <li key={o.thread_id}>
            <a class="order-card" href={`#/order/${o.thread_id}`}>
              <div class="row space">
                <b>{o.customer || o.topic_name || `#${o.thread_id}`}</b>
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
      {!loading && page < totalPages && (
        <button class="btn wide" onClick={() => { const p = page + 1; setPage(p); load(p, search, true); }}>
          Tải thêm
        </button>
      )}
      {!loading && !visible.length && !err && <p class="muted center">Không có đơn nào</p>}
    </div>
  );
}
