// Feed ĐƠN + THANH TOÁN của 1 khách (trang chi tiết khách) — trọng tâm của trang.
// 3 kiểu xem y dashboard Đơn (full/compact/ultra — card dùng chung detail/OrderCards)
// + dòng thanh toán 💵 xen kẽ đúng thứ tự thời gian, nhóm theo ngày ở view ultra.
// Data: GET /api/customers/{key}/feed (server_app/customer_feed.py).
import { useEffect, useRef, useState } from "preact/hooks";
import { getCustomerFeed, listOrderImages, type CustFeedItem, type OrderImage } from "../api";
import { money, fmtDateTimeVN, fmtRelative, isRecent } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, SkeletonList } from "../ui/states";
import { PhotoViewer } from "./PhotoViewer";
import {
  type OrderRow, statusLabel, LastAction, CardBody, CompactBody, UltraBody,
  InvoiceMini, dayKeyOf, orderDayLabel, NEW_ORDER_SEC,
} from "./OrderCards";

type View = "full" | "compact" | "ultra";
const _VIEWS: { m: View; ic: string; t: string }[] = [
  { m: "full", ic: "▤", t: "Đầy đủ" },
  { m: "compact", ic: "▦", t: "Gọn" },
  { m: "ultra", ic: "☰", t: "Siêu gọn" },
];

const PAY_METHOD_VI: Record<string, string> = {
  tm: "tiền mặt", cash: "tiền mặt",
  ck: "chuyển khoản", transfer: "chuyển khoản", banktransfer: "chuyển khoản",
};

// Dòng thanh toán trong feed — nổi bật kiểu "biên lai": link sang đơn tương ứng
function PaymentRow({ p }: { p: Extract<CustFeedItem, { kind: "payment" }> }) {
  const method = PAY_METHOD_VI[(p.method || "").toLowerCase()] || p.code || p.method || "";
  return (
    <a class="feed-pay" href={`#/order/${p.thread_id}`}>
      <span class="feed-pay-ic"><Icon name="wallet" size={16} /></span>
      <span class="feed-pay-main">
        <b class="feed-pay-amt">+{money(p.amount)}đ</b>
        {method && <span class="feed-pay-m"> · {method}</span>}
        <span class="muted small"> · đơn #{p.thread_id}</span>
      </span>
      <span class="muted small feed-pay-when">
        {p.by ? `${p.by} · ` : ""}{p.at ? fmtRelative(p.at) : ""}
      </span>
    </a>
  );
}

/** Nhóm feed theo NGÀY (dùng cho view ultra) — đơn lấy created, payment lấy at. */
function groupFeedByDay(items: CustFeedItem[]): { key: string; label: string; items: CustFeedItem[] }[] {
  const out: { key: string; label: string; items: CustFeedItem[] }[] = [];
  for (const it of items) {
    const key = dayKeyOf(it.kind === "order" ? it.order.created : it.at);
    const last = out[out.length - 1];
    if (last && last.key === key) last.items.push(it);
    else out.push({ key, label: orderDayLabel(key), items: [it] });
  }
  return out;
}

export function CustomerFeed({ ckey }: { ckey: string }) {
  const [items, setItems] = useState<CustFeedItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<View>(() => {
    const v = localStorage.getItem("cust_view");
    return v === "compact" || v === "ultra" ? (v as View) : "full";
  });
  const seq = useRef(0);

  const load = async (p: number, replace = false) => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const r = await getCustomerFeed(ckey, p);
      if (my !== seq.current) return;
      setItems((prev) => (replace || p === 1 ? r.items : [...prev, ...r.items]));
      setPage(r.page);
      setTotalPages(r.total_pages);
      setTotal(r.total);
    } catch { /* mất mạng — giữ nguyên */ } finally {
      if (my === seq.current) setLoading(false);
    }
  };
  useEffect(() => { load(1, true); }, [ckey]);

  // Realtime: đơn/thanh toán của khách đổi → tải lại trang 1 (giữ các trang sau nếu đã tải? đơn giản: reset)
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "order_changed" || e.type === "orders_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(() => load(1, true), 400);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [ckey]);

  const setViewMode = (m: View) => { setView(m); localStorage.setItem("cust_view", m); };

  // PhotoViewer khi bấm thumbnail card (giống dashboard)
  const [viewer, setViewer] = useState<{ threadId: string; images: OrderImage[]; start: number } | null>(null);
  const openThumb = async (e: Event, o: OrderRow, atId?: number) => {
    e.preventDefault(); e.stopPropagation();
    try {
      const imgs = await listOrderImages(o.thread_id);
      if (!imgs.length) return;
      const start = Math.max(0, atId ? imgs.findIndex((x) => x.id === atId) : 0);
      setViewer({ threadId: String(o.thread_id), images: imgs, start });
    } catch { /* im */ }
  };

  const renderItem = (it: CustFeedItem) => {
    if (it.kind === "payment") return <li key={`p-${it.thread_id}-${it.ts}`}><PaymentRow p={it} /></li>;
    const o = it.order as OrderRow;
    const isNew = isRecent(o.created, NEW_ORDER_SEC);
    if (view === "ultra") {
      return (
        <li key={o.thread_id}>
          <a data-oid={o.thread_id} class="order-card ultra" href={`#/order/${o.thread_id}`}>
            <UltraBody o={o} search="" />
          </a>
        </li>
      );
    }
    if (view === "compact") {
      return (
        <li key={o.thread_id}>
          <a data-oid={o.thread_id} class={`order-card compact${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
            <CompactBody o={o} search="" sort="created" isNew={isNew} openThumb={openThumb} />
          </a>
        </li>
      );
    }
    return (
      <li key={o.thread_id}>
        <a data-oid={o.thread_id} class={`order-card two-col${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
          <div class="card-main">
            <LastAction o={o} />
            <CardBody o={o} search="" stt={statusLabel(o)} isNew={isNew} openThumb={openThumb} />
          </div>
          <div class="card-inv"><InvoiceMini o={o} /></div>
        </a>
      </li>
    );
  };

  return (
    <section class="cust-feed">
      <div class="row space cf-head">
        <b class="cf-title"><Icon name="clipboard" size={16} /> Đơn & thanh toán {total > 0 ? <span class="muted small">({total})</span> : null}</b>
        <div class="view-slider" role="group" aria-label="Kiểu xem">
          {_VIEWS.map((v) => (
            <button key={v.m} class={view === v.m ? "vs-seg on" : "vs-seg"} title={v.t} aria-pressed={view === v.m} onClick={() => setViewMode(v.m)}>{v.ic}</button>
          ))}
        </div>
      </div>

      {loading && !items.length && <SkeletonList rows={4} />}
      <ul class="order-list">
        {view === "ultra"
          ? groupFeedByDay(items).map((g) => (
              <li key={`g-${g.key}`} class="order-day-group">
                <div class="order-day-head">{g.label} <span class="muted small">({g.items.length})</span></div>
                <ul class="order-list">{g.items.map(renderItem)}</ul>
              </li>
            ))
          : items.map(renderItem)}
      </ul>
      {loading && items.length > 0 && <Loading />}
      {!loading && page < totalPages && (
        <button class="btn small wide" onClick={() => load(page + 1)}>Tải thêm</button>
      )}
      {!loading && !items.length && <EmptyState>Chưa có đơn nào của khách này</EmptyState>}

      {viewer && (
        <PhotoViewer images={viewer.images} start={viewer.start} base={`/api/order/${viewer.threadId}`} editable
          onKindChange={(id, kind) => setViewer((v: any) => v && ({ ...v, images: v.images.map((x: any) => (x.id === id ? { ...x, kind } : x)) }))}
          onClose={() => setViewer(null)} />
      )}
    </section>
  );
}
