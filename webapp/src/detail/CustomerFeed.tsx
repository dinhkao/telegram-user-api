// Feed ĐƠN + THANH TOÁN của 1 khách (trang chi tiết khách) — trọng tâm của trang.
// 3 kiểu xem y dashboard Đơn (full/compact/ultra — card dùng chung detail/OrderCards)
// + card thanh toán 💵 xen kẽ đúng thứ tự thời gian, nhóm theo ngày ở view ultra.
// Mỗi card chốt SỔ NỢ: đơn = +tổng → nợ sau; thanh toán = −tiền → nợ sau.
// DÂY LIÊN KẾT: payment ↔ đơn của nó (cùng trong feed) nối bằng rail dọc bên trái
// (đo vị trí thật bằng ResizeObserver, chia lane tránh đè nhau) — bấm chip đơn trên
// payment card cuộn + nháy card đơn. Data: GET /api/customers/{key}/feed.
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { getCustomerFeed, listOrderImages, orderImageUrl, type CustFeedItem, type OrderImage } from "../api";
import { money, fmtRelative, fmtDateTimeVN, isRecent } from "../format";
import { onRealtime } from "../realtime";
import { fastScrollToEl } from "../scroll";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, SkeletonList } from "../ui/states";
import { PhotoViewer } from "./PhotoViewer";
import {
  type OrderRow, statusLabel, LastAction, CardBody, CompactBody, TaskBadges,
  InvoiceMini, NEW_ORDER_SEC,
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

// RAIL PHẢI NGOÀI card — sổ cái dọc: NGANG card = số tiền sự kiện (xám, +tổng
// đơn / −tiền thu); Ở KHE giữa card này và card TRÊN = SỐ NỢ SAU sự kiện (đỏ
// khi >0, xanh khi 0, '—' xám khi bản ghi cũ thiếu số — KHÔNG bịa 0).
// (feed mới→cũ nên "sau sự kiện" = phía trên card — đọc từ dưới lên đúng dòng thời gian)
// data-debt trên số nợ → lượt đo SVG vẽ ĐOẠN line chấm-tới-chấm đúng màu
// (đỏ đang nợ / xanh sạch / xám không rõ) — không đứt ở header ngày, đổi màu
// CHÍNH XÁC tại chấm.
function Rail({ delta, deltaCls, debt, est }: {
  delta: string | null; deltaCls?: string; debt: number | null | undefined; est?: boolean;
}) {
  return (
    <span class="feed-rail">
      {/* SỐ nợ = XÁM đậm (lượng); trạng thái ở chấm + line màu (data-debt).
          est = số TÍNH LẠI từ chuỗi neo mốc KV (bản ghi cũ thiếu số) → hiện ≈ */}
      {debt == null
        ? <span class="fd-gap fd-na" data-debt="na" title="Không đủ mốc để tính">—</span>
        : <span class="fd-gap" data-debt={Number(debt) > 0 ? "owe" : "ok"}
            title={est ? "Số tính lại từ lịch sử (bản ghi cũ không lưu số nợ)" : undefined}>
            {est ? "≈" : ""}{money(Number(debt))}
          </span>}
      {delta && <span class={"feed-delta " + (deltaCls || "")}>{delta}</span>}
    </span>
  );
}

/** "HH:mm · DD/MM" từ chuỗi thời gian bất kỳ (dựa fmtDateTimeVN). */
const hmd = (v?: string | null): string => {
  const s = fmtDateTimeVN(v || "");
  const t = (s.match(/\d{2}:\d{2}/) || [""])[0];
  const d = (s.match(/\d{2}\/\d{2}/) || [""])[0];
  return t && d ? `${t} · ${d}` : t || d;
};

// Card thanh toán — kích thước ĐỒNG BỘ với card đơn của view (cùng radius/padding/
// nhịp margin). Chip "đơn #id" → cuộn tới card đơn.
function PaymentCard({ p, hasOrderInFeed, onJump }: {
  p: PayItem; hasOrderInFeed: boolean; onJump: (tid: number) => void;
}) {
  const m = payMethod(p);
  return (
    <div class="order-card feed-pay" data-pay-tid={p.thread_id}>
      <span class="fu-time">{hmd(p.at)}</span>
      <div class="feed-pay-row">
        <span class="feed-pay-ic"><Icon name="wallet" size={16} /></span>
        <span class="feed-pay-main">
          <b class="feed-pay-amt">−{money(p.amount)}</b>
          {m && <span class="muted"> · {m}</span>}
        </span>
        <button class={"feed-pay-link" + (hasOrderInFeed ? " in-feed" : "")}
          title={hasOrderInFeed ? "Cuộn tới đơn trong danh sách" : "Mở đơn"}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onJump(p.thread_id); }}>
          <Icon name="link" size={12} /> #{p.thread_id}
        </button>
      </div>
      <div class="feed-pay-meta muted small">{p.by ? `${p.by} · ` : ""}{p.at ? fmtRelative(p.at) : ""}</div>
    </div>
  );
}

// ── KHOẢNG TRỐNG THỜI GIAN = TUYẾN TÍNH THẬT: cao 14px/ngày (2 ngày = 28px,
// 1 tháng ≈ 420px — chấp nhận kéo dài để trung thực; cap an toàn 1400px ≈ 100
// ngày, nhãn vẫn nói số thật). Đoạn line nợ qua khe vẽ NÉT ĐỨT, màu giữ nguyên
// (nợ vẫn treo suốt khoảng nghỉ). ts = epoch giây từ server.
const gapDays = (newer?: number, older?: number): number =>
  newer && older ? Math.round((newer - older) / 86400) : 0;
const gapLabel = (d: number) =>
  d >= 60 ? `${Math.round(d / 30)} tháng` : d >= 14 ? `${Math.round(d / 7)} tuần` : `${d} ngày`;
const gapSpacer = (d: number, key: string) => (
  <li key={key} class="feed-gap-li" style={{ height: `${Math.min(d * 14, 1400)}px` }} aria-hidden="true">
    <span class="fg-label">· {gapLabel(d)} ·</span>
  </li>
);

type Rope = { d: string; x0: number; y1: number; y2: number };

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
  // đoạn line tiến trình nợ (chấm-tới-chấm, màu theo mốc DƯỚI = trạng thái của khoảng đó)
  const [debtSegs, setDebtSegs] = useState<{ x: number; y1: number; y2: number; st: string }[]>([]);
  const orderIdsInFeed = new Set(items.filter((i) => i.kind === "order").map((i: any) => i.order.thread_id));
  useLayoutEffect(() => {
    const ul = listRef.current;
    if (!ul) { setRopes([]); return; }
    const measure = () => {
      const box = ul.getBoundingClientRect();
      // (card TRÊN = payment vì feed sắp mới→cũ; card DƯỚI = đơn của nó)
      const segs: { x0: number; y1: number; y2: number }[] = [];
      for (const payEl of Array.from(ul.querySelectorAll<HTMLElement>("[data-pay-tid]"))) {
        const tid = payEl.getAttribute("data-pay-tid");
        const orderEl = ul.querySelector<HTMLElement>(`a[data-oid="${tid}"]`);
        if (!orderEl) continue;
        const a = payEl.getBoundingClientRect(), b = orderEl.getBoundingClientRect();
        const up = a.top <= b.top ? a : b, down = a.top <= b.top ? b : a;
        segs.push({
          x0: Math.min(up.left, down.left) - box.left,   // mép trái card
          y1: up.bottom - box.top - 9,                   // DƯỚI-trái card trên
          y2: down.top - box.top + 9,                    // TRÊN-trái card dưới
        });
      }
      // chia lane: 2 dây giao nhau thì bụng cong ở lane khác (tối đa 3, xoay vòng)
      segs.sort((x, y) => x.y1 - y.y1);
      const laneEnds: number[] = [];
      const out: Rope[] = [];
      for (const s of segs) {
        let lane = laneEnds.findIndex((end) => end <= s.y1);
        if (lane === -1) { lane = laneEnds.length < 3 ? laneEnds.length : out.length % 3; laneEnds.push(0); }
        laneEnds[lane] = s.y2;
        // Đường cong MỀM (không gãy khúc): lượn từ dưới-trái card trên ra bụng
        // cong ở lề (xg ÂM = tràn vào padding trang, sát mép màn hình) rồi lượn
        // vào trên-trái card dưới. bend lớn → cong thoải, hết nhìn "vuông".
        const xg = -9 + lane * 3;
        const bend = Math.min(18, (s.y2 - s.y1) / 2);
        const d = `M ${s.x0} ${s.y1} Q ${xg} ${s.y1} ${xg} ${s.y1 + bend}`
          + (s.y2 - bend > s.y1 + bend ? ` V ${s.y2 - bend}` : "")
          + ` Q ${xg} ${s.y2} ${s.x0} ${s.y2}`;
        out.push({ d, x0: s.x0, y1: s.y1, y2: s.y2 });
      }
      setRopes(out);
      // ── line tiến trình nợ: nối các chấm số nợ theo đúng vị trí đo được ──
      const pts = Array.from(ul.querySelectorAll<HTMLElement>(".fd-gap"))
        .map((el) => { const r = el.getBoundingClientRect(); return { y: (r.top + r.bottom) / 2 - box.top, st: el.getAttribute("data-debt") || "na" }; })
        .sort((a, b) => a.y - b.y);
      const x = box.width - 7.5;   // tâm cột chấm (chấm ::after right 3.5px + bán kính 4)
      // Luật màu: đi TỪ DƯỚI LÊN (đúng dòng thời gian cũ→mới) — qua chấm đỏ thì
      // line ĐỎ cho tới khi gặp chấm xanh thì chuyển XANH, và cứ thế
      // (đoạn TRÊN mỗi chấm = màu chấm đó, tới chấm kế trên thì đổi).
      // Luật line (đi TỪ DƯỚI LÊN): mốc nợ>0 → đoạn trên nó ĐỎ LIỀN; chạm mốc
      // nợ=0 → đoạn trên nó NÉT ĐỨT (không còn nợ treo) tới khi phát sinh nợ
      // lại; không rõ → đứt xám. Kiểu nét/màu do CSS theo st (dl-owe/dl-ok/dl-na).
      const dl: { x: number; y1: number; y2: number; st: string }[] = [];
      for (let i = 0; i < pts.length - 1; i++)
        dl.push({ x, y1: pts[i].y, y2: pts[i + 1].y, st: pts[i + 1].st });
      setDebtSegs(dl);
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
      const debt = it.debt_after != null ? Number(it.debt_after) : null;
      const rail = <Rail delta={`−${money(it.amount)}`} deltaCls="d-ok" debt={debt} est={it.debt_est} />;
      if (view === "ultra") {
        return (
          <li key={`p-${it.thread_id}-${it.ts}`} class="feed-item" data-pay-tid={it.thread_id}>
            <button class="order-card ultra feed-pay-ultra" onClick={() => jumpToOrder(it.thread_id)}>
              <span class="fu-time">{hmd(it.at)}</span>
              <div class="ultra-row">
                <span class="feed-pay-ic"><Icon name="wallet" size={13} /></span>
                <span class="ultra-text"><b class="feed-pay-amt">−{money(it.amount)}</b>{payMethod(it) ? ` · ${payMethod(it)}` : ""}</span>
              </div>
            </button>
            {rail}
          </li>
        );
      }
      return (
        <li key={`p-${it.thread_id}-${it.ts}`} class="feed-item">
          <PaymentCard p={it} hasOrderInFeed={orderIdsInFeed.has(it.thread_id)} onJump={jumpToOrder} />
          {rail}
        </li>
      );
    }
    const o = it.order as OrderRow;
    const isNew = isRecent(o.created, NEW_ORDER_SEC);
    const rail = <Rail delta={o.total ? `+${o.total}` : null} deltaCls="d-owe" debt={it.debt_after} est={it.debt_est} />;
    if (view === "ultra") {
      // ultra: thumb (ưu tiên ảnh SOẠN HÀNG) trước khối badges+text; giờ HH:mm góc phải-trên
      const text = (o.text || o.topic_name || `#${o.thread_id}`).replace(/\s+/g, " ").trim();
      const thumbId = (o.soan_img_ids && o.soan_img_ids[0])
        || (o.thumb_image_ids && o.thumb_image_ids[0]) || o.thumb_image_id;
      return (
        <li key={o.thread_id} class="feed-item">
          <a data-oid={o.thread_id} class="order-card ultra feed-ultra" href={`#/order/${o.thread_id}`}>
            <span class="fu-time">{hmd(o.created)}</span>
            <div class="fu-row">
              {thumbId ? (
                <img class="fu-thumb" src={orderImageUrl(o.thread_id, thumbId, "thumb")} loading="lazy" alt=""
                  onClick={(e) => openThumb(e, o, thumbId as number)} />
              ) : null}
              <div class="fu-main">
                <TaskBadges o={o} />
                <div class="fu-text">{text}</div>
              </div>
            </div>
          </a>
          {rail}
        </li>
      );
    }
    if (view === "compact") {
      return (
        <li key={o.thread_id} class="feed-item">
          <a data-oid={o.thread_id} class={`order-card compact feed-card${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
            <CompactBody o={o} search="" sort="created" isNew={isNew} openThumb={openThumb} />
          </a>
          {rail}
        </li>
      );
    }
    return (
      <li key={o.thread_id} class="feed-item">
        <a data-oid={o.thread_id} class={`order-card two-col feed-card${isNew ? " new-order" : ""}`} href={`#/order/${o.thread_id}`}>
          <div class="card-main">
            <LastAction o={o} />
            <CardBody o={o} search="" stt={statusLabel(o)} isNew={isNew} openThumb={openThumb} />
          </div>
          <div class="card-inv"><InvoiceMini o={o} /></div>
        </a>
        {rail}
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
      <div class={"cf-body" + (hasRopes ? " has-ropes" : "") + (items.length ? " has-items" : "")}>
        {/* dây cong nối payment ↔ đơn: dưới-trái card trên → vòng lề trái → trên-trái card dưới */}
        {(hasRopes || debtSegs.length > 0) && (
          <svg class="feed-ropes" aria-hidden="true">
            {debtSegs.map((s, i) => (
              <line key={`d${i}`} class={`dl-${s.st}`} x1={s.x} x2={s.x} y1={s.y1} y2={s.y2} />
            ))}
            {ropes.map((r, i) => (
              <g key={i}>
                <path d={r.d} />
                <circle cx={r.x0} cy={r.y1} r="2.6" />
                <circle cx={r.x0} cy={r.y2} r="2.6" />
              </g>
            ))}
          </svg>
        )}
        <ul class="order-list" ref={listRef}>
          {items.flatMap((it, i) => {
            const d = i > 0 ? gapDays(items[i - 1].ts, it.ts) : 0;
            return d >= 2 ? [gapSpacer(d, `gap-${i}`), renderItem(it)] : [renderItem(it)];
          })}
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
