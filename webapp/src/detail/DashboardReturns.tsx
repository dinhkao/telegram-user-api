// Card PHIẾU TRẢ HÀNG chen vào dashboard đơn (#/orders) theo đúng mốc thời gian tạo.
// Chỉ bật khi dashboard sắp theo "Mới tạo" + chip "Tất cả" (các chip Chưa soạn/giao/…
// là trạng thái đơn, phiếu trả không có). Dữ liệu: GET /api/returns (listAllReturns,
// 20/trang, mới→cũ) — chỉ tải thêm trang khi đơn đã cuộn xuống cũ hơn phiếu cũ nhất
// đang có. Ô tìm lọc phiếu client-side (khách / mã SP / mã HĐ). Card → #/tra-hang/:id.
// Realtime: return_changed / customer_changed / resync → tải lại.
import { useEffect, useState } from "preact/hooks";
import { listAllReturns, soVN, type ReturnSlip } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { type OrderRow, dayKeyOf, groupOrdersByDay, orderDayLabel } from "./OrderCards";

export type DashEntry = { t: "o"; o: OrderRow } | { t: "r"; r: ReturnSlip };
type View = "full" | "compact" | "ultra";

const ts = (s?: string | null) => { const n = Date.parse(s || ""); return Number.isFinite(n) ? n : 0; };

// Cache module — quay lại dashboard vẽ ngay, khỏi tải lại
let cache: { rows: ReturnSlip[]; page: number; totalPages: number } | null = null;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((f) => f());

async function loadPage(page: number): Promise<void> {
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const r = await listAllReturns(page);
      const prev = page > 1 && cache ? cache.rows : [];
      const seen = new Set(prev.map((x) => x.id));
      cache = { rows: [...prev, ...r.returns.filter((x) => !seen.has(x.id))], page: r.page, totalPages: r.total_pages };
      notify();
    } catch { /* mất mạng — dashboard đơn vẫn chạy, lần sau thử lại */ }
    finally { inflight = null; }
  })();
  return inflight;
}

onRealtime((e) => {
  if (e.type === "return_changed" || e.type === "customer_changed" || e.type === "resync") {
    if (cache) void loadPage(1);
  }
});

/** Phiếu trả cần chen vào dashboard: nằm trong khoảng thời gian các đơn đã tải
 *  (cũ nhất = `oldest`; `exhausted` = hết đơn thì lấy hết) + khớp ô tìm. */
export function useDashboardReturns(active: boolean, orders: OrderRow[], exhausted: boolean, search: string, custKey?: string | null): ReturnSlip[] {
  const [, force] = useState(0);
  useEffect(() => {
    const f = () => force((x) => x + 1);
    listeners.add(f);
    return () => { listeners.delete(f); };
  }, []);
  const oldest = orders.length ? Math.min(...orders.map((o) => ts(o.created) || Infinity)) : Infinity;
  useEffect(() => {
    if (!active) return;
    if (!cache) { void loadPage(1); return; }
    // Đơn đã cuộn cũ hơn phiếu cũ nhất đang có → tải thêm trang phiếu trả
    const last = cache.rows[cache.rows.length - 1];
    const need = exhausted || (last && ts(last.created_at) > oldest);
    if (need && cache.page < cache.totalPages) void loadPage(cache.page + 1);
  }, [active, oldest, exhausted, cache?.page, cache?.rows.length]);
  if (!active || !cache || !orders.length) return [];
  const q = foldVN(search.trim());
  return cache.rows.filter((r) => {
    if (!exhausted && ts(r.created_at) < oldest) return false;
    if (custKey && String(r.customer_key) !== custKey) return false;   // đang lọc theo MÃ khách
    if (!q) return true;
    return foldVN(`${r.customer_name || ""} ${r.kv_invoice_code || ""} ${(r.items || []).map((x) => x.sp).join(" ")} ${r.note || ""}`).includes(q);
  });
}

/** Trộn đơn (đã sắp mới→cũ theo created) với phiếu trả (mới→cũ) thành 1 dòng thời gian. */
export function interleave(orders: OrderRow[], returns: ReturnSlip[]): DashEntry[] {
  const out: DashEntry[] = [];
  let j = 0;
  for (const o of orders) {
    const t = ts(o.created);
    while (j < returns.length && ts(returns[j].created_at) >= t) out.push({ t: "r", r: returns[j++] });
    out.push({ t: "o", o });
  }
  while (j < returns.length) out.push({ t: "r", r: returns[j++] });
  return out;
}

/** Nhóm theo ngày cho view siêu gọn. Không có phiếu trả → giữ nguyên groupOrdersByDay. */
export function groupEntriesByDay(orders: OrderRow[], returns: ReturnSlip[], sort: Parameters<typeof groupOrdersByDay>[1]) {
  if (!returns.length) {
    return groupOrdersByDay(orders, sort).map((g) => ({ ...g, count: g.orders.length, entries: g.orders.map((o): DashEntry => ({ t: "o", o })) }));
  }
  const out: { key: string; label: string; count: number; entries: DashEntry[] }[] = [];
  for (const e of interleave(orders, returns)) {
    const key = dayKeyOf(e.t === "o" ? e.o.created : e.r.created_at || "");
    let g = out[out.length - 1];
    if (!g || g.key !== key) { g = { key, label: orderDayLabel(key), count: 0, entries: [] }; out.push(g); }
    g.entries.push(e);
    if (e.t === "o") g.count++;
  }
  return out;
}

export function ReturnDashCard({ r, view }: { r: ReturnSlip; view: View }) {
  const items = (r.items || []).map((x) => `${x.sp} ×${soVN(x.sl)}`).join(", ");
  const status = r.kv_invoice_code
    ? <span class="pk-badge sx"><Icon name="receipt" size={11} /> {r.kv_invoice_code}</span>
    : <span class="pk-badge pack"><Icon name="edit" size={11} /> Nháp</span>;
  if (view === "ultra") {
    return (
      <a class="order-card ultra ret-dash" href={`#/tra-hang/${r.id}`}>
        <div class="ultra-row">
          <span class="ret-dash-tag"><Icon name="refresh" size={12} /> Trả</span>
          <span class="ultra-text">{r.customer_name || r.customer_key} · {items}</span>
          <span class="ret-amt">−{soVN(r.total)}</span>
        </div>
      </a>
    );
  }
  return (
    <a class={`order-card ret-dash${view === "compact" ? " compact" : ""}`} href={`#/tra-hang/${r.id}`}>
      <div class="ret-card-top">
        <span class="ret-cust">
          <span class="ret-dash-tag"><Icon name="refresh" size={12} /> Trả hàng</span> {r.customer_name || r.customer_key}
          {status}
        </span>
        <span class="ret-amt">−{soVN(r.total)}</span>
      </div>
      <div class="ret-card-sub muted small">
        {items}
        {r.created_by ? ` · ${r.created_by}` : ""}
        {r.created_at ? ` · ${r.created_at.slice(11, 16)}` : ""}
        {r.goods_handled_at ? " · đã xử lý hàng" : " · chưa xử lý hàng"}
      </div>
      {view === "full" && r.note && <div class="ret-card-note"><Icon name="note" size={12} /> {r.note}</div>}
    </a>
  );
}
