// Dashboard NỘP TIỀN (#/nop-tien) — danh sách mọi đơn đã giao nhưng chưa nộp.
// Tối ưu cho thao tác tại quầy: không cần mở chi tiết đơn để ghi nhận 4 tình huống
// thường gặp của bước Nộp tiền. Hai nhánh cần ảnh dùng chung NopTienWizard.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { getJSON, postJSON } from "../api";
import { onRealtime } from "../realtime";
import { foldVN, fmtDateTimeVN, fmtRelative, money } from "../format";
import { ErrorState, EmptyState, SkeletonList } from "../ui/states";
import { SearchBar } from "../ui/SearchBar";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import { NopTienWizard } from "../detail/NopTienWizard";
import type { OrderRow } from "../detail/OrderCards";

type PhotoBranch = "tra_tien_mat" | "co_ky_toa";
type QuickAction = "khong_ky_toa" | "chieu_lay_tien";
type DashboardData = { orders: OrderRow[]; total: number; stale?: boolean };
type Scope = "all" | "pending" | "later" | "today" | "older";

let dashboardCache: DashboardData | null = null;

function orderLabel(o: OrderRow): string {
  return (o.text || o.topic_name || `Đơn #${o.thread_id}`).replace(/\s+/g, " ").trim();
}

function deliveredAt(o: OrderRow): string {
  return o.giao_at || o.updated_at?.toString() || o.created || "";
}

function isWaitingLater(o: OrderRow): boolean {
  return (o.nop_note || "").toLowerCase().split(";")[0] === "chieu_lay_tien";
}

function isUnpaidOrder(o: Partial<OrderRow>): boolean {
  // Khớp semantics server của filter=chua_nop: đã giao, chưa nộp, có khách,
  // và chỉ nhận dữ liệu từ mốc workflow hiện hành.
  return !!o.customer_key && !!o.giao && !o.nop && String(o.created || "") >= "2026-06-01";
}

function sortDashboardOrders(orders: OrderRow[]): OrderRow[] {
  return [...orders].sort((a, b) => String(b.giao_at || b.created || "").localeCompare(String(a.giao_at || a.created || "")));
}

function isToday(value: string): boolean {
  if (!value) return false;
  const d = new Date(value);
  const now = new Date();
  return d.toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" })
    === now.toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" });
}

async function getAllUnpaid(): Promise<DashboardData> {
  const first = await getJSON("/api/orders?page=1&limit=200&filter=chua_nop&sort=giao_at", { cache: false });
  const pages = Number(first.total_pages) || 1;
  const rest = pages > 1
    ? await Promise.all(Array.from({ length: pages - 1 }, (_, i) =>
      getJSON(`/api/orders?page=${i + 2}&limit=200&filter=chua_nop&sort=giao_at`, { cache: false }),
    ))
    : [];
  return {
    orders: [first, ...rest].flatMap((p: any) => p.orders || []),
    total: Number(first.total) || 0,
    stale: !!first._stale,
  };
}

export function NopTienDashboard() {
  const [data, setData] = useState<DashboardData | null>(dashboardCache);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<Scope>("pending");
  const [activeWizard, setActiveWizard] = useState<{ threadId: string; branch: PhotoBranch | null } | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const loadSeq = useRef(0);
  const reloadTimer = useRef<number | null>(null);

  const reload = async () => {
    const seq = ++loadSeq.current;
    try {
      const next = await getAllUnpaid();
      if (seq !== loadSeq.current) return;
      dashboardCache = next;
      setData(next);
      setErr("");
    } catch (ex: any) {
      if (seq === loadSeq.current) setErr(ex?.message || "Không tải được danh sách đơn chưa nộp");
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
      const matches = !!row && isUnpaidOrder(row as OrderRow);
      let orders = prev.orders;
      if (matches) {
        const next = row as OrderRow;
        orders = index >= 0 ? prev.orders.map((o, i) => i === index ? next : o) : [...prev.orders, next];
        orders = sortDashboardOrders(orders);
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
      if (e.type === "order_changed") {
        applyOrderEvent(e.thread_id, e.row);
      } else if (e.type === "orders_changed" || e.type === "resync") {
        scheduleReload();
      }
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
    if (scope === "pending") return !isWaitingLater(o);
    if (scope === "later") return isWaitingLater(o);
    if (scope === "today") return isToday(deliveredAt(o));
    if (scope === "older") return !isToday(deliveredAt(o));
    return true;
  }), [orders, normalized, scope]);

  const todayCount = orders.filter((o) => isToday(deliveredAt(o))).length;
  const olderCount = orders.length - todayCount;
  const laterCount = orders.filter(isWaitingLater).length;
  const pendingCount = orders.length - laterCount;
  const pendingValue = orders.reduce((sum, o) => sum + Number(o.remaining || 0), 0);

  const quick = async (o: OrderRow, action: QuickAction) => {
    const key = `${o.thread_id}:${action}`;
    if (busy[key]) return;
    setBusy((prev) => ({ ...prev, [key]: true }));
    try {
      await postJSON("/api/order/task", {
        thread_id: Number(o.thread_id), type: "nop_tien",
        note: action, done: action !== "chieu_lay_tien",
      }, { queueable: false });
      toast(action === "chieu_lay_tien" ? "Đã ghi: chiều lấy tiền" : "Đã ghi: không ký toa", "ok");
      dashboardCache = null;
      await reload();
    } catch (ex: any) {
      toast(ex?.message || "Không ghi được trạng thái nộp tiền", "err");
    } finally {
      setBusy((prev) => { const next = { ...prev }; delete next[key]; return next; });
    }
  };

  const openPhoto = (threadId: number, branch: PhotoBranch) => {
    setActiveWizard({ threadId: String(threadId), branch });
  };

  if (err && !data) return <ErrorState msg={err} onRetry={reload} />;
  if (!data) return <SkeletonList rows={5} />;

  return (
    <div class="nopdash">
      <section class="nopdash-hero">
        <div class="nopdash-kicker"><Icon name="wallet" size={14} /> SỔ NỘP TIỀN · CẬP NHẬT TRỰC TIẾP</div>
        <div class="nopdash-headline">
          <div>
            <h1>Nộp tiền</h1>
            <p>Gom việc còn tồn thành một màn hình thao tác nhanh.</p>
          </div>
          <div class="nopdash-count"><strong>{orders.length}</strong><span>đơn đang chờ</span><em>{money(pendingValue)} đ</em></div>
        </div>
        <div class="nopdash-progress"><i style={{ width: `${orders.length ? Math.min(100, Math.max(8, 100 - Math.min(90, orders.length * 2))) : 100}%` }} /></div>
        <div class="nopdash-meta"><span><b>{todayCount}</b> giao hôm nay</span><span><b>{olderCount}</b> tồn từ trước</span><button onClick={reload}><Icon name="refresh" size={13} /> Làm mới</button></div>
      </section>

      <div class="nopdash-toolbar">
        <SearchBar value={query} onInput={setQuery} placeholder="Tìm khách, nội dung hoặc mã đơn…" />
        <div class="nopdash-filters" role="tablist" aria-label="Lọc đơn chưa nộp">
          <button class={scope === "all" ? "active" : ""} onClick={() => setScope("all")}>Tất cả <b>{orders.length}</b></button>
          <button class={scope === "pending" ? "active" : ""} onClick={() => setScope("pending")}>Chưa nộp <b>{pendingCount}</b></button>
          <button class={scope === "later" ? "active" : ""} onClick={() => setScope("later")}>Chiều lấy tiền <b>{laterCount}</b></button>
          <button class={scope === "today" ? "active" : ""} onClick={() => setScope("today")}>Hôm nay <b>{todayCount}</b></button>
          <button class={scope === "older" ? "active" : ""} onClick={() => setScope("older")}>Tồn trước <b>{olderCount}</b></button>
        </div>
      </div>

      {data.stale && <p class="nopdash-stale">⚠️ Đang hiển thị dữ liệu lưu sẵn — sẽ đồng bộ lại khi có mạng.</p>}
      {err && <p class="nopdash-stale error">{err}</p>}

      {visible.length === 0 ? (
        <div class="nopdash-clear"><span>✓</span><b>{query || scope !== "all" ? "Không có đơn phù hợp" : "Đã dọn sạch danh sách"}</b><small>{query || scope !== "all" ? "Thử đổi bộ lọc hoặc từ khoá." : "Tất cả đơn đã giao đều đã được ghi nhận nộp tiền."}</small></div>
      ) : (
        <div class="nopdash-list">
          {visible.map((o, index) => {
            const label = orderLabel(o);
            const age = fmtRelative(deliveredAt(o));
            const old = !isToday(deliveredAt(o));
            const waitingLater = isWaitingLater(o);
            const busyNoSign = !!busy[`${o.thread_id}:khong_ky_toa`];
            const busyLater = !!busy[`${o.thread_id}:chieu_lay_tien`];
            return (
              <article class={`nopdash-card${old ? " is-old" : ""}${waitingLater ? " is-later" : ""}`} key={o.thread_id} style={{ animationDelay: `${Math.min(index, 10) * 35}ms` }}>
                <div class="nopdash-card-top">
                  <span class="nopdash-rank">{String(index + 1).padStart(2, "0")}</span>
                  <div class="nopdash-order-copy">
                    <div class={`nopdash-kind ${waitingLater ? "later" : "pending"}`}>
                      <Icon name={waitingLater ? "clock" : "banknote"} size={12} />
                      {waitingLater ? "CHIỀU LẤY TIỀN" : "CHƯA NỘP"}
                    </div>
                    <a href={`#/order/${o.thread_id}`} class="nopdash-order-title">{label}</a>
                    <div class="nopdash-sub"><span class="nopdash-customer">{o.customer || "Chưa gán khách"}</span><span>#{o.thread_id}</span><span>{age || fmtDateTimeVN(o.created)}</span></div>
                  </div>
                  <span class="nopdash-amount">{money(o.remaining)} đ</span>
                  <a class="nopdash-open" href={`#/order/${o.thread_id}`} title="Mở chi tiết đơn"><Icon name="chevronRight" size={17} /></a>
                </div>
                <div class="nopdash-card-bottom">
                  <div class="nopdash-status"><span class="nopdash-status-dot" /> {waitingLater ? "Đã hẹn chiều lấy tiền" : "Đã giao"}{o.giao_by ? ` · ${o.giao_by}` : ""}<span class="nopdash-status-age">{waitingLater ? "Đang chờ thu" : old ? "Cần ưu tiên" : "Mới giao"}</span></div>
                  <div class="nopdash-actions">
                    <button class="nopdash-action primary" onClick={() => openPhoto(o.thread_id, "tra_tien_mat")}><Icon name="camera" size={14} /> Đã thu đủ</button>
                    <button class="nopdash-action photo" onClick={() => openPhoto(o.thread_id, "co_ky_toa")}><Icon name="edit" size={14} /> Có ký toa</button>
                    <button class="nopdash-action" disabled={busyNoSign} onClick={() => quick(o, "khong_ky_toa")}>{busyNoSign ? "…" : "Không ký toa"}</button>
                    <button class="nopdash-action later" disabled={busyLater} onClick={() => quick(o, "chieu_lay_tien")}>{busyLater ? "…" : "Chiều lấy"}</button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {activeWizard && <NopTienWizard key={`${activeWizard.threadId}:${activeWizard.branch || "menu"}`} threadId={activeWizard.threadId}
        initialBranch={activeWizard.branch || undefined} onClose={() => setActiveWizard(null)} onDone={() => { dashboardCache = null; void reload(); }} />}
    </div>
  );
}
