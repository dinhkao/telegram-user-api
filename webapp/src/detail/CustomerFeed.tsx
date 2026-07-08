// Feed ĐƠN + THANH TOÁN của 1 khách (trang chi tiết khách) — trọng tâm của trang.
// 3 kiểu xem y dashboard Đơn (full/compact/ultra — card dùng chung detail/OrderCards)
// + card thanh toán 💵 xen kẽ đúng thứ tự thời gian, nhóm theo ngày ở view ultra.
// Mỗi card chốt SỔ NỢ: đơn = +tổng → nợ sau; thanh toán = −tiền → nợ sau.
// DÂY LIÊN KẾT: payment ↔ đơn của nó (cùng trong feed) nối bằng rail dọc bên trái
// (đo vị trí thật bằng ResizeObserver, chia lane tránh đè nhau) — bấm chip đơn trên
// payment card cuộn + nháy card đơn. Data: GET /api/customers/{key}/feed.
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { getCustomerFeed, listOrderImages, type CustFeedItem, type OrderImage } from "../api";
import { money, fmtRelative, isRecent } from "../format";
import { onRealtime } from "../realtime";
import { fastScrollToEl } from "../scroll";
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

type PayItem = Extract<CustFeedItem, { kind: "payment" }>;
const payMethod = (p: PayItem) => PAY_METHOD_VI[(p.method || "").toLowerCase()] || p.code || p.method || "";

// Chốt sổ cuối card: bên trái = biến động của sự kiện, bên phải = NỢ SAU sự kiện
function LedgerFoot({ delta, deltaCls, debtAfter }: { delta: string; deltaCls: string; debtAfter: number | null | undefined }) {
  return (
    <div class="feed-ledger">
      <span class={`fl-delta ${deltaCls}`}>{delta}</span>
      {debtAfter != null && (
        <span class="fl-debt">Nợ sau: <b class={Number(debtAfter) > 0 ? "owe" : "paid-ok"}>{money(Number(debtAfter))}đ</b></span>
      )}
    </div>
  );
}

// Card thanh toán — kích thước ĐỒNG BỘ với card đơn của view (cùng radius/padding/
// nhịp margin); nội dung 1 dòng + chốt sổ. Chip "đơn #id" → cuộn tới card đơn.
function PaymentCard({ p, hasOrderInFeed, onJump }: {
  p: PayItem; hasOrderInFeed: boolean; onJump: (tid: number) => void;
}) {
  const m = payMethod(p);
  return (
    <div class="order-card feed-pay" data-pay-tid={p.thread_id}>
      <div class="feed-pay-row">
        <span class="feed-pay-ic"><Icon name="wallet" size={16} /></span>
        <span class="feed-pay-main">
          <b class="feed-pay-amt">Thanh toán {money(p.amount)}đ</b>
          {m && <span class="muted"> · {m}</span>}
        </span>
        <button class={"feed-pay-link" + (hasOrderInFeed ? " in-feed" : "")}
          title={hasOrderInFeed ? "Cuộn tới đơn trong danh sách" : "Mở đơn"}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onJump(p.thread_id); }}>
          <Icon name="link" size={12} /> đơn #{p.thread_id}
        </button>
      </div>
      <LedgerFoot delta={`−${money(p.amount)}đ`} deltaCls="paid-ok"
        debtAfter={p.new_debt != null ? Number(p.new_debt) : null} />
      <div class="feed-pay-meta muted small">{p.by ? `${p.by} · ` : ""}{p.at ? fmtRelative(p.at) : ""}</div>
    </div>
  );
}

/** Nhóm feed theo NGÀY (view ultra) — đơn lấy created, payment lấy at. */
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

type Rope = { top: number; height: number; lane: number };

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

  // ── DÂY LIÊN KẾT payment ↔ đơn: đo vị trí card thật → rail dọc bên trái ──
  const listRef = useRef<HTMLUListElement>(null);
  const [ropes, setRopes] = useState<Rope[]>([]);
  const orderIdsInFeed = new Set(items.filter((i) => i.kind === "order").map((i: any) => i.order.thread_id));
  useLayoutEffect(() => {
    const ul = listRef.current;
    if (!ul) { setRopes([]); return; }
    const measure = () => {
      const base = ul.getBoundingClientRect().top;
      const segs: { top: number; bottom: number }[] = [];
      for (const payEl of Array.from(ul.querySelectorAll<HTMLElement>("[data-pay-tid]"))) {
        const tid = payEl.getAttribute("data-pay-tid");
        const orderEl = ul.querySelector<HTMLElement>(`a[data-oid="${tid}"]`);
        if (!orderEl) continue;
        const a = payEl.getBoundingClientRect(), b = orderEl.getBoundingClientRect();
        const top = Math.min(a.top, b.top) + Math.min(a.height, 40) / 2 - base;
        const bottom = Math.max(a.bottom, b.bottom) - Math.min(b.height, 40) / 2 - base;
        if (bottom - top > 8) segs.push({ top, bottom });
      }
      // chia lane: 2 dây giao nhau thì nằm lane khác (tối đa 3, xoay vòng)
      segs.sort((x, y) => x.top - y.top);
      const laneEnds: number[] = [];
      const out: Rope[] = [];
      for (const s of segs) {
        let lane = laneEnds.findIndex((end) => end <= s.top);
        if (lane === -1) { lane = laneEnds.length < 3 ? laneEnds.length : out.length % 3; laneEnds.push(0); }
        laneEnds[lane] = s.bottom;
        out.push({ top: s.top, height: s.bottom - s.top, lane });
      }
      setRopes(out);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(ul);
    return () => ro.disconnect();
  }, [items, view]);

  const jumpToOrder = (tid: number) => {
    const el = listRef.current?.querySelector<HTMLElement>(`a[data-oid="${tid}"]`);
    if (el) {
      fastScrollToEl(el, "center");
      el.classList.add("flash-target");
      setTimeout(() => el.classList.remove("flash-target"), 2000);
    } else {
      window.location.hash = `#/order/${tid}`;   // đơn chưa nằm trong trang đã tải → mở thẳng
    }
  };

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
    if (it.kind === "payment") {
      if (view === "ultra") {
        return (
          <li key={`p-${it.thread_id}-${it.ts}`} data-pay-tid={it.thread_id}>
            <button class="order-card ultra feed-pay-ultra" onClick={() => jumpToOrder(it.thread_id)}>
              <div class="ultra-row">
                <span class="feed-pay-ic"><Icon name="wallet" size={13} /></span>
                <span class="ultra-text"><b class="feed-pay-amt">+{money(it.amount)}đ</b>{payMethod(it) ? ` · ${payMethod(it)}` : ""}</span>
              </div>
              {it.new_debt != null && <span class="ultra-debt">nợ {money(Number(it.new_debt))}đ</span>}
            </button>
          </li>
        );
      }
      return (
        <li key={`p-${it.thread_id}-${it.ts}`}>
          <PaymentCard p={it} hasOrderInFeed={orderIdsInFeed.has(it.thread_id)} onJump={jumpToOrder} />
        </li>
      );
    }
    const o = it.order as OrderRow;
    const isNew = isRecent(o.created, NEW_ORDER_SEC);
    const ledger = it.debt_after != null || o.total ? (
      <LedgerFoot delta={o.total ? `+${o.total}đ` : ""} deltaCls="owe" debtAfter={it.debt_after} />
    ) : null;
    if (view === "ultra") {
      return (
        <li key={o.thread_id}>
          <a data-oid={o.thread_id} class="order-card ultra" href={`#/order/${o.thread_id}`}>
            <UltraBody o={o} search="" />
            {it.debt_after != null && <span class="ultra-debt">nợ {money(Number(it.debt_after))}đ</span>}
          </a>
        </li>
      );
    }
    if (view === "compact") {
      return (
        <li key={o.thread_id}>
          <a data-oid={o.thread_id} class={`order-card compact feed-card${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
            <CompactBody o={o} search="" sort="created" isNew={isNew} openThumb={openThumb} />
            {ledger}
          </a>
        </li>
      );
    }
    return (
      <li key={o.thread_id}>
        <a data-oid={o.thread_id} class={`order-card two-col feed-card${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
          <div class="card-main">
            <LastAction o={o} />
            <CardBody o={o} search="" stt={statusLabel(o)} isNew={isNew} openThumb={openThumb} />
          </div>
          <div class="card-inv"><InvoiceMini o={o} /></div>
          {ledger}
        </a>
      </li>
    );
  };

  const hasRopes = ropes.length > 0;
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
      <div class={"cf-body" + (hasRopes ? " has-ropes" : "")}>
        {/* rail dọc nối payment ↔ đơn của nó (đo vị trí thật, chia lane) */}
        {ropes.map((r, i) => (
          <span key={i} class="feed-rope" style={{ top: `${r.top}px`, height: `${r.height}px`, left: `${2 + r.lane * 5}px` }} />
        ))}
        <ul class="order-list" ref={listRef}>
          {view === "ultra"
            ? groupFeedByDay(items).map((g) => (
                <li key={`g-${g.key}`} class="order-day-group">
                  <div class="order-day-head">{g.label} <span class="muted small">({g.items.length})</span></div>
                  <ul class="order-list">{g.items.map(renderItem)}</ul>
                </li>
              ))
            : items.map(renderItem)}
        </ul>
      </div>
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
