// Khách hàng — tìm kiếm + công nợ. GET /api/customers?search=&sort=recent. Tap → lọc đơn theo tên.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money, fmtTime } from "../format";

export function Customers() {
  const [search, setSearch] = useState("");
  const [customers, setCustomers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const reqSeq = useRef(0);

  const load = async (q: string) => {
    const seq = ++reqSeq.current;
    setLoading(true);
    setErr("");
    try {
      const r = await getJSON(`/api/customers?search=${encodeURIComponent(q)}&limit=40&sort=recent`, { cache: false });
      if (seq !== reqSeq.current) return;
      setCustomers(r.customers || []);
    } catch (ex: any) {
      if (seq === reqSeq.current) setErr(ex.message);
    } finally {
      if (seq === reqSeq.current) setLoading(false);
    }
  };

  useEffect(() => {
    load("");
  }, []);

  const onSearch = (q: string) => {
    setSearch(q);
    if (q.length === 1) return;
    load(q);
  };

  return (
    <div>
      <header class="topbar">
        <input class="search" type="search" placeholder="🔍 Tìm khách hàng…" value={search} onInput={(e: any) => onSearch(e.target.value)} />
      </header>
      {err && <p class="error">{err}</p>}
      <ul class="order-list">
        {customers.map((c) => (
          <li key={c.key}>
            <div class="order-card">
              <div class="row space">
                <b>{c.name}</b>
                {c.debt != null && (
                  <span class={Number(c.debt) > 0 ? "owe" : "muted"}>
                    nợ {money(Number(c.debt) || 0)}đ
                  </span>
                )}
              </div>
              <div class="row space">
                <span class="muted small">{c.kh_id ? `KV: ${c.kh_id} · ` : ""}{c.key}</span>
                {c.last_order_at && <span class="muted small">📦 {fmtTime(c.last_order_at)}</span>}
              </div>
              <a class="btn small" href={`#/orders`} onClick={() => localStorage.setItem("pending_search", c.name)}>
                Xem đơn của khách này
              </a>
            </div>
          </li>
        ))}
      </ul>
      {loading && <p class="muted center">Đang tải…</p>}
      {!loading && !customers.length && !err && <p class="muted center">Không thấy khách</p>}
    </div>
  );
}
