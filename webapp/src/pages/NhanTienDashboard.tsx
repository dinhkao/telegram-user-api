// Dashboard NHẬN TIỀN (#/nhan-tien) — đơn đã nộp tiền nhưng văn phòng chưa
// hoàn tất bước Nhận tiền / Gửi toa. Dùng filter chua_nhan của API đơn để khớp
// đúng workflow server, thao tác nhanh ngay trên từng card.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { getJSON, postJSON } from "../api";
import { onRealtime } from "../realtime";
import { foldVN, fmtDateTimeVN, fmtRelative, money } from "../format";
import { ErrorState, EmptyState, SkeletonList } from "../ui/states";
import { SearchBar } from "../ui/SearchBar";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import type { OrderRow } from "../detail/OrderCards";

type DashboardData = { orders: OrderRow[]; total: number; stale?: boolean };
type Scope = "all" | "pending" | "receipt" | "today" | "older";

let dashboardCache: DashboardData | null = null;

function orderLabel(o: OrderRow): string {
  return (o.text || o.topic_name || `Đơn #${o.thread_id}`).replace(/\s+/g, " ").trim();
}

function activityAt(o: OrderRow): string {
  const raw = o.updated_at;
  const epoch = Number(raw);
  if (Number.isFinite(epoch) && epoch > 1_000_000_000_000) return new Date(epoch).toISOString();
  return o.giao_at || o.created || "";
}

function isReceiptOrder(o: OrderRow): boolean {
  const note = (o.nop_note || "").toLowerCase().split(";")[0];
  return note === "co_ky_toa" || note === "khong_ky_toa";
}

function isWaitingReceive(o: Partial<OrderRow>): boolean {
  return !!o.customer_key && !!o.nop && !o.nhan && String(o.created || "") >= "2026-06-01";
}

function isToday(value: string): boolean {
  if (!value) return false;
  const d = new Date(value);
  const now = new Date();
  return d.toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" })
    === now.toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" });
}

function sortOrders(orders: OrderRow[]): OrderRow[] {
  return [...orders].sort((a, b) => String(b.updated_at || b.giao_at || b.created || "")
    .localeCompare(String(a.updated_at || a.giao_at || a.created || "")));
}

async function getAllWaitingReceive(): Promise<DashboardData> {
  const first = await getJSON("/api/orders?page=1&limit=200&filter=chua_nhan&sort=updated", { cache: false });
  const pages = Number(first.total_pages) || 1;
  const rest = pages > 1
    ? await Promise.all(Array.from({ length: pages - 1 }, (_, i) =>
      getJSON(`/api/orders?page=${i + 2}&limit=200&filter=chua_nhan&sort=updated`, { cache: false }),
    ))
    : [];
  return {
    orders: [first, ...rest].flatMap((p: any) => p.orders || []),
    total: Number(first.total) || 0,
    stale: !!first._stale,
  };
}

export function NhanTienDashboard() {
  const [data, setData] = useState<DashboardData | null>(dashboardCache);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<Scope>("pending");
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const loadSeq = useRef(0);
  const reloadTimer = useRef<number | null>(null);

  const reload = async () => {
    const seq = ++loadSeq.current;
    try {
      const next = await getAllWaitingReceive();
      if (seq !== loadSeq.current) return;
      dashboardCache = next;
      setData(next);
      setErr("");
    } catch (ex: any) {
      if (seq === loadSeq.current) setErr(ex?.message || "Không tải được danh sách chờ nhận tiền");
    }
  };

  const scheduleReload = () => {
    if (reloadTimer.current != null) window.clearTimeout(reloadTimer.current);
    reloadTimer.current = window.setTimeout(() => {
      reloadTimer.current = null;
      void reload();
    }, 350);
  };

  const applyOrderEvent = (threadId: string, row: any | null) => {
    const id = String(row?.thread_id ?? threadId);
    setData((prev) => {
      if (!prev) return prev;
      const index = prev.orders.findIndex((o) => String(o.thread_id) === id);
      const matches = !!row && isWaitingReceive(row as OrderRow);
      let orders = prev.orders;
      if (matches) {
        const next = row as OrderRow;
        orders = index >= 0 ? prev.orders.map((o, i) => i === index ? next : o) : [...prev.orders, next];
        orders = sortOrders(orders);
      } else if (index >= 0) {
        orders = prev.orders.filter((_, i) => i !== index);
      }
      if (orders === prev.orders) return prev;
      const nextData = { ...prev, orders, total: orders.length, stale: false };
      dashboardCache = nextData;
      return nextData;
    });
  };

  useEffect(() => {
    void reload();
    const off = onRealtime((e) => {
      if (e.type === "order_changed") applyOrderEvent(e.thread_id, e.row);
      else if (e.type === "orders_changed" || e.type === "resync") scheduleReload();
    });
    return () => {
      off();
      if (reloadTimer.current != null) window.clearTimeout(reloadTimer.current);
    };
  }, []);

  const orders = data?.orders || [];
  const normalized = foldVN(query.trim());
  const visible = useMemo(() => orders.filter((o) => {
    const haystack = foldVN(`${o.customer} ${o.text} ${o.topic_name} ${o.thread_id}`);
    if (normalized && !haystack.includes(normalized)) return false;
    if (scope === "receipt") return isReceiptOrder(o);
    if (scope === "today") return isToday(activityAt(o));
    if (scope === "older") return !isToday(activityAt(o));
    return true;
  }), [orders, normalized, scope]);

  const todayCount = orders.filter((o) => isToday(activityAt(o))).length;
  const olderCount = orders.length - todayCount;
  const receiptCount = orders.filter(isReceiptOrder).length;
  const cashCount = orders.length - receiptCount;
  const receiveValue = orders.reduce((sum, o) => sum + Number(o.remaining || 0), 0);

  const complete = async (o: OrderRow) => {
    const note = isReceiptOrder(o) ? "gtr" : "";
    const key = `${o.thread_id}:${note || "receive"}`;
    if (busy[key]) return;
    setBusy((prev) => ({ ...prev, [key]: true }));
    try {
      await postJSON("/api/order/task", {
        thread_id: Number(o.thread_id), type: "nhan_tien", note, done: true,
      }, { queueable: false });
      toast(note ? "Đã ghi: gửi toa" : "Đã ghi: đã nhận tiền", "ok");
      dashboardCache = null;
      await reload();
    } catch (ex: any) {
      toast(ex?.message || "Không ghi được bước nhận tiền", "err");
    } finally {
      setBusy((prev) => { const next = { ...prev }; delete next[key]; return next; });
    }
  };

  if (err && !data) return <ErrorState msg={err} onRetry={reload} />;
  if (!data) return <SkeletonList rows={5} />;

  return (
    <div class="nopdash nhandash">
      <section class="nopdash-hero">
        <div class="nopdash-kicker"><Icon name="wallet" size={14} /> SỔ NHẬN TIỀN · CẬP NHẬT TRỰC TIẾP</div>
        <div class="nopdash-headline">
          <div>
            <h1>Nhận tiền</h1>
            <p>Gom đơn đã nộp để văn phòng nhận tiền hoặc gửi toa nhanh.</p>
          </div>
          <div class="nopdash-count"><strong>{orders.length}</strong><span>đơn đang chờ</span><em>{money(receiveValue)} đ</em></div>
        </div>
        <div class="nopdash-progress"><i style={{ width: `${orders.length ? Math.min(100, Math.max(8, 100 - Math.min(90, orders.length * 2))) : 100}%` }} /></div>
        <div class="nopdash-meta"><span><b>{cashCount}</b> nhận tiền</span><span><b>{receiptCount}</b> gửi toa</span><button onClick={reload}><Icon name="refresh" size={13} /> Làm mới</button></div>
      </section>

      <div class="nopdash-toolbar">
        <SearchBar value={query} onInput={setQuery} placeholder="Tìm khách, nội dung hoặc mã đơn…" />
        <div class="nopdash-filters" role="tablist" aria-label="Lọc đơn chờ nhận tiền">
          <button class={scope === "all" ? "active" : ""} onClick={() => setScope("all")}>Tất cả <b>{orders.length}</b></button>
          <button class={scope === "pending" ? "active" : ""} onClick={() => setScope("pending")}>Chờ nhận <b>{cashCount}</b></button>
          <button class={scope === "receipt" ? "active" : ""} onClick={() => setScope("receipt")}>Gửi toa <b>{receiptCount}</b></button>
          <button class={scope === "today" ? "active" : ""} onClick={() => setScope("today")}>Hôm nay <b>{todayCount}</b></button>
          <button class={scope === "older" ? "active" : ""} onClick={() => setScope("older")}>Tồn trước <b>{olderCount}</b></button>
        </div>
      </div>

      {data.stale && <p class="nopdash-stale">⚠️ Đang hiển thị dữ liệu lưu sẵn — sẽ đồng bộ lại khi có mạng.</p>}
      {err && <p class="nopdash-stale error">{err}</p>}

      {visible.length === 0 ? (
        <div class="nopdash-clear"><span>✓</span><b>{query || scope !== "all" ? "Không có đơn phù hợp" : "Đã nhận hết danh sách"}</b><small>{query || scope !== "all" ? "Thử đổi bộ lọc hoặc từ khoá." : "Không còn đơn nào chờ nhận tiền hoặc gửi toa."}</small></div>
      ) : (
        <div class="nopdash-list">
          {visible.map((o, index) => {
            const label = orderLabel(o);
            const age = fmtRelative(activityAt(o));
            const old = !isToday(activityAt(o));
            const receipt = isReceiptOrder(o);
            const actionKey = `${o.thread_id}:${receipt ? "gtr" : "receive"}`;
            return (
              <article class={`nopdash-card${old ? " is-old" : ""}${receipt ? " is-receipt" : ""}`} key={o.thread_id} style={{ animationDelay: `${Math.min(index, 10) * 35}ms` }}>
                <div class="nopdash-card-top">
                  <span class="nopdash-rank">{String(index + 1).padStart(2, "0")}</span>
                  <div class="nopdash-order-copy">
                    <div class={`nopdash-kind ${receipt ? "later" : "pending"}`}>
                      <Icon name={receipt ? "edit" : "banknote"} size={12} />
                      {receipt ? "GỬI TOA" : "CHỜ NHẬN TIỀN"}
                    </div>
                    <a href={`#/order/${o.thread_id}`} class="nopdash-order-title">{label}</a>
                    <div class="nopdash-sub"><span class="nopdash-customer">{o.customer || "Chưa gán khách"}</span><span>#{o.thread_id}</span><span>{age || fmtDateTimeVN(o.created)}</span></div>
                  </div>
                  <span class="nopdash-amount">{money(o.remaining)} đ</span>
                  <a class="nopdash-open" href={`#/order/${o.thread_id}`} title="Mở chi tiết đơn"><Icon name="chevronRight" size={17} /></a>
                </div>
                <div class="nopdash-card-bottom">
                  <div class="nopdash-status"><span class="nopdash-status-dot" /> Đã nộp{o.nop_by ? ` · ${o.nop_by}` : ""}<span class="nopdash-status-age">{receipt ? "Cần gửi toa" : old ? "Cần ưu tiên" : "Mới nộp"}</span></div>
                  <div class="nopdash-actions nhandash-actions">
                    <button class="nopdash-action primary" disabled={!!busy[actionKey]} onClick={() => complete(o)}>
                      <Icon name={receipt ? "edit" : "banknote"} size={14} /> {busy[actionKey] ? "…" : receipt ? "Đã gửi toa" : "Đã nhận tiền"}
                    </button>
                    <a class="nopdash-action nhandash-detail" href={`#/order/${o.thread_id}`}>Mở chi tiết</a>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
