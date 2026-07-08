// Feed ĐƠN + THANH TOÁN của 1 khách (trang chi tiết khách) — trọng tâm của trang.
// 3 kiểu xem y dashboard Đơn (full/compact/ultra — card dùng chung detail/OrderCards)
// + card thanh toán 💵 xen kẽ đúng thứ tự thời gian, nhóm theo ngày ở view ultra.
// Mỗi card chốt SỔ NỢ: đơn = +tổng → nợ sau; thanh toán = −tiền → nợ sau.
// DÂY LIÊN KẾT: payment ↔ đơn của nó (cùng trong feed) nối bằng rail dọc bên trái
// (đo vị trí thật bằng ResizeObserver, chia lane tránh đè nhau) — bấm chip đơn trên
// payment card cuộn + nháy card đơn. Data: GET /api/customers/{key}/feed.
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { getCustomerFeed, listOrderImages, orderImageUrl, type CustFeedItem, type OrderImage } from "../api";
import { money, fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { fastScrollToEl } from "../scroll";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, SkeletonList } from "../ui/states";
import { PhotoViewer } from "./PhotoViewer";
import { type OrderRow, TaskBadges, dayKeyOf, orderDayLabel } from "./OrderCards";

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
          est = số TÍNH LẠI từ chuỗi neo mốc KV (bản ghi cũ thiếu số) → hiện ≈.
          Số + chấm là HẠT TRƯỢT: JS (applyBeads) translateY nó chạy giữa 2 số
          phát sinh kề nó theo chiều cuộn — xem khối HẠT NỢ trong CustomerFeed. */}
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

/** Giờ HH:mm (ngày đã có header ngày lo — card chỉ cần giờ). */
const hmd = (v?: string | null): string => (fmtDateTimeVN(v || "").match(/\d{2}:\d{2}/) || [""])[0];

// ── KHOẢNG TRỐNG THỜI GIAN = TUYẾN TÍNH THẬT: cao 14px/ngày (2 ngày = 28px,
// 1 tháng ≈ 420px — chấp nhận kéo dài để trung thực; cap an toàn 1400px ≈ 100
// ngày, nhãn vẫn nói số thật). Đoạn line nợ qua khe vẽ NÉT ĐỨT, màu giữ nguyên
// (nợ vẫn treo suốt khoảng nghỉ). ts = epoch giây từ server.
const gapDays = (newer?: number, older?: number): number =>
  newer && older ? Math.round((newer - older) / 86400) : 0;
const gapLabel = (d: number) =>
  d >= 60 ? `${Math.round(d / 30)} tháng` : d >= 14 ? `${Math.round(d / 7)} tuần` : `${d} ngày`;
// Khe đủ chỗ trượt (≥5 ngày ≈ 70px): SỐ NỢ của khe (= nợ sau sự kiện cũ ở đáy)
// chuyển HẲN vào khe làm số trượt DUY NHẤT (sticky, kẹp 2 đầu, đáp xuống cạnh
// chấm mốc ở đáy — item dưới chỉ giữ chấm, không lặp số). Khe nhỏ: số ở đáy như cũ.
const gapSpacer = (d: number, key: string) => (
  <li key={key} class="feed-gap-li" style={{ height: `${Math.min(d * 14, 1400)}px` }} aria-hidden="true">
    <span class="fg-label">· {gapLabel(d)} ·</span>
  </li>
);

// Mốc 6/7/2026 00:00 VN — trước đó phiếu thu CHƯA lưu số nợ (tính năng thêm
// 6/7/2026): chèn 1 dòng lưu ý tại điểm feed vượt qua mốc này khi cuộn.
const DEBT_FEATURE_TS = new Date("2026-07-06T00:00:00+07:00").getTime() / 1000;

/** Ngày (DD/MM/YYYY) của 1 item feed. */
const dayOf = (it: CustFeedItem): string => dayKeyOf(it.kind === "order" ? it.order.created : it.at);
const DEBT_NOTE_TEXT = "⚠️ Từ đây trở về trước (trước 6/7/2026): số nợ theo phiếu có thể thiếu hoặc là "
  + "số ước lượng (≈) — tính năng lưu nợ tại thời điểm thu mới có từ 6/7/2026.";

type Rope = { d: string; x0: number; y1: number; y2: number };

// Render 1 item feed (card 2 dòng + rail nợ) — DÙNG CHUNG cho feed stream và
// popup trang lịch. handlers: openThumb (PhotoViewer) + jumpToOrder (cuộn/mở đơn).
export function renderFeedItem(it: CustFeedItem, h: {
  openThumb: (e: Event, o: OrderRow, atId?: number) => void;
  jumpToOrder: (tid: number) => void;
}) {
    if (it.kind === "payment") {
      const debt = it.debt_after != null ? Number(it.debt_after) : null;
      return (
        <li key={`p-${it.thread_id}-${it.ts}`} class="feed-item" data-pay-tid={it.thread_id}>
          <button class="order-card ultra feed-pay-ultra" onClick={() => h.jumpToOrder(it.thread_id)}>
            <span class="fu-time">{hmd(it.at)}</span>
            <div class="ultra-row">
              <span class="feed-pay-ic"><Icon name="wallet" size={13} /></span>
              <span class="ultra-text"><b class="feed-pay-amt">−{money(it.amount)}</b>{payMethod(it) ? ` · ${payMethod(it)}` : ""}</span>
            </div>
            {/* dòng 2 — cao ĐỒNG BỘ với card đơn (badges + text) */}
            <div class="fu-text muted">{it.by || "\u00a0"}</div>
          </button>
          <Rail delta={`−${money(it.amount)}`} deltaCls="d-ok" debt={debt} est={it.debt_est} />
        </li>
      );
    }
    const o = it.order as OrderRow;
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
                onClick={(e) => h.openThumb(e, o, thumbId as number)} />
            ) : null}
            <div class="fu-main">
              <TaskBadges o={o} />
              <div class="fu-text">{text}</div>
            </div>
          </div>
        </a>
        <Rail delta={o.total ? `+${o.total}` : null} deltaCls="d-owe" debt={it.debt_after} est={it.debt_est} />
      </li>
    );
}

export function CustomerFeed({ ckey }: { ckey: string }) {
  const [items, setItems] = useState<CustFeedItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
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

  // ── HẠT NỢ TRƯỢT: số nợ đen + chấm (fd-gap) trượt dọc line giữa 2 SỐ PHÁT
  // SINH kề nó (delta trên ↔ delta dưới) theo chiều cuộn. CSS sticky không làm
  // được (đoạn trượt vượt ranh giới li) → JS: đo mốc 1 lần (trong measure), mỗi
  // frame cuộn chỉ tính clamp + translateY (compositor — không reflow). ──
  const beadsRef = useRef<{ el: HTMLElement; nat: number; top: number; bot: number }[]>([]);
  const ulTopRef = useRef(0);   // toạ độ tài liệu của ul lúc đo
  // đoạn LINE nợ bám theo chấm: meta đo tĩnh (el 2 đầu + y gốc) + cache node <line>
  const segMetaRef = useRef<{ topEl: HTMLElement; botEl: HTMLElement; y1: number; y2: number }[]>([]);
  const lineNodesRef = useRef<SVGLineElement[] | null>(null);
  const applyBeads = () => {
    // đường ghim = GIỮA MÀN HÌNH — hạt bắt đầu trượt khi tới giữa màn,
    // không phải lúc sắp trôi khỏi mép trên
    const pin = window.innerHeight * 0.45;
    const s = window.scrollY + pin - ulTopRef.current;   // đường ghim trong toạ độ ul
    let floor = -Infinity;   // hạt không được vượt/đè hạt TRÊN nó (xếp hàng dọc dây)
    const tOf = new Map<HTMLElement, number>();
    for (const b of beadsRef.current) {
      const target = Math.min(Math.max(Math.min(Math.max(s, b.top), b.bot), floor), b.bot);
      floor = target + 20;
      const t = target - b.nat;
      tOf.set(b.el, t);
      b.el.style.transform = t ? `translateY(${t}px)` : "";
    }
    // ── line bám chấm: đầu đoạn dịch đúng bằng translate của chấm đó ──
    const metas = segMetaRef.current;
    let nodes = lineNodesRef.current;
    if (!nodes || nodes.length !== metas.length) {
      const svg = listRef.current?.parentElement?.querySelector("svg.feed-ropes");
      nodes = svg ? (Array.from(svg.querySelectorAll("line")) as SVGLineElement[]) : [];
      lineNodesRef.current = nodes;
    }
    const n = Math.min(nodes.length, metas.length);
    for (let i = 0; i < n; i++) {
      const m = metas[i];
      nodes[i].setAttribute("y1", String(m.y1 + (tOf.get(m.topEl) || 0)));
      nodes[i].setAttribute("y2", String(m.y2 + (tOf.get(m.botEl) || 0)));
    }
  };
  useEffect(() => {
    // vòng rAF LIÊN TỤC khi đang cuộn (scroll event trên WebView Android thưa
    // lúc fling → hạt giật): đọc scrollY mỗi frame, đứng yên ~20 frame thì nghỉ
    let raf = 0, running = false, lastY = -1, idle = 0;
    const tick = () => {
      const y = window.scrollY;
      if (y !== lastY) { lastY = y; idle = 0; applyBeads(); }
      else if (++idle > 20) { running = false; return; }
      raf = requestAnimationFrame(tick);
    };
    const onScroll = () => { if (!running) { running = true; idle = 0; raf = requestAnimationFrame(tick); } };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, []);

  // ── DÂY LIÊN KẾT payment ↔ đơn: đo vị trí card thật → rail dọc bên trái ──
  const listRef = useRef<HTMLUListElement>(null);
  const [ropes, setRopes] = useState<Rope[]>([]);
  // đoạn line tiến trình nợ (chấm-tới-chấm, màu theo mốc DƯỚI = trạng thái của khoảng đó)
  const [debtSegs, setDebtSegs] = useState<{ x: number; y1: number; y2: number; st: string }[]>([]);
  // SỐ 0 LẶP LẠI ngay dưới biến động làm nợ ≠ 0 trở lại — đóng khung quãng sạch
  // nợ ở cả 2 đầu (mốc 0 gốc dưới + bản lặp trên). Vẽ SVG text+circle, tĩnh.
  const [repZeros, setRepZeros] = useState<{ x: number; y: number; t: string }[]>([]);
  // render lại <line> (sau measure) đè y tĩnh lên attr đã dịch → áp lại ngay
  useLayoutEffect(() => { applyBeads(); }, [debtSegs]);
  useLayoutEffect(() => {
    const ul = listRef.current;
    if (!ul) { setRopes([]); return; }
    const measure = () => {
      // đo ở TRẠNG THÁI GỐC — transform của hạt làm sai getBoundingClientRect
      for (const b of beadsRef.current) b.el.style.transform = "";
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
        .map((el) => { const r = el.getBoundingClientRect(); return { el, y: (r.top + r.bottom) / 2 - box.top, st: el.getAttribute("data-debt") || "na" }; })
        .sort((a, b) => a.y - b.y);
      const x = box.width - 7.5;   // tâm cột chấm (chấm ::after right 3.5px + bán kính 4)
      // Luật màu: đi TỪ DƯỚI LÊN (đúng dòng thời gian cũ→mới) — qua chấm đỏ thì
      // line ĐỎ cho tới khi gặp chấm xanh thì chuyển XANH, và cứ thế
      // (đoạn TRÊN mỗi chấm = màu chấm đó, tới chấm kế trên thì đổi).
      // Luật line (đi TỪ DƯỚI LÊN): mốc nợ>0 → đoạn trên nó ĐỎ LIỀN; chạm mốc
      // nợ=0 → CẮT (không vẽ — hết nợ treo) tới khi phát sinh nợ lại;
      // không rõ → đứt xám. Kiểu nét/màu do CSS theo st (dl-owe/dl-na).
      // vị trí các SỐ PHÁT SINH (delta) — mốc "biến động" để vẽ lại line sau khi cắt
      const deltas = Array.from(ul.querySelectorAll<HTMLElement>(".feed-delta"))
        .map((el) => { const r = el.getBoundingClientRect(); return { el, y: (r.top + r.bottom) / 2 - box.top }; })
        .sort((a, b) => a.y - b.y);
      const dl: { x: number; y1: number; y2: number; st: string }[] = [];
      const segMeta: { topEl: HTMLElement; botEl: HTMLElement; y1: number; y2: number }[] = [];
      const repz: { x: number; y: number; t: string }[] = [];
      for (let i = 0; i < pts.length - 1; i++) {
        // Mốc nợ = 0 → CẮT line, chỉ đúng quãng thật sự sạch nợ: từ mốc 0 lên tới
        // BIẾN ĐỘNG gần nhất phía trên (sự kiện làm nợ ≠ 0 trở lại) — từ đó trở
        // lên nợ treo lại → vẽ tiếp; và LẶP LẠI SỐ 0 ngay dưới biến động đó
        // (ngay-trước-biến-động nợ vẫn 0) để đóng khung quãng sạch ở cả 2 đầu.
        // dl/segMeta push CÙNG NHAU để index khớp node <line> (line bám chấm).
        if (pts[i + 1].st === "ok") {
          const span = deltas.filter((d) => d.y > pts[i].y + 1 && d.y < pts[i + 1].y - 1);
          const low = span.length ? span[span.length - 1] : null;   // biến động THẤP NHẤT trong quãng
          if (low) {
            const st = pts[i].st === "na" ? "na" : "owe";
            // quãng sạch đủ dài mới lặp (sát nhau thì số 0 gốc ngay đó rồi);
            // có chấm lặp → line kéo xuống ĐÚNG TÂM chấm (nối liền, không hụt)
            const rep = pts[i + 1].y - low.y > 70;
            const yEnd = rep ? low.y + 18 : low.y - 8;
            dl.push({ x, y1: pts[i].y, y2: yEnd, st });
            segMeta.push({ topEl: pts[i].el, botEl: low.el, y1: pts[i].y, y2: yEnd });
            if (rep) repz.push({ x, y: low.y + 18, t: pts[i + 1].el.textContent || "0" });
          }
          continue;
        }
        dl.push({ x, y1: pts[i].y, y2: pts[i + 1].y, st: pts[i + 1].st });
        segMeta.push({ topEl: pts[i].el, botEl: pts[i + 1].el, y1: pts[i].y, y2: pts[i + 1].y });
      }
      setRepZeros(repz);
      segMetaRef.current = segMeta;
      lineNodesRef.current = null;   // node <line> render lại sau setState → requery
      setDebtSegs(dl);
      // ── mốc HẠT NỢ TRƯỢT: chỉ số ĐANG NỢ (đỏ) trượt, chạy giữa 2 NÚT kề nó.
      // Nút chặn = số phát sinh (delta) + mốc nợ=0 (đứng yên tại chỗ — sổ đã
      // tất toán là điểm chết trên dây, hạt khác không xuyên qua). '—' bỏ hẳn. ──
      const rail: { bead: boolean; el: HTMLElement; y: number }[] = [];
      for (const el of Array.from(ul.querySelectorAll<HTMLElement>(".fd-gap, .feed-delta"))) {
        const isDebt = el.classList.contains("fd-gap");
        if (isDebt && el.classList.contains("fd-na")) continue;   // '—' không có thông tin → đứng yên
        const r = el.getBoundingClientRect();
        rail.push({ bead: isDebt && el.getAttribute("data-debt") === "owe",
          el, y: (r.top + r.bottom) / 2 - box.top });
      }
      rail.sort((a, b) => a.y - b.y);
      const beads: { el: HTMLElement; nat: number; top: number; bot: number }[] = [];
      let prevKnot: number | null = null;
      for (let i = 0; i < rail.length; i++) {
        if (!rail[i].bead) { prevKnot = rail[i].y; continue; }
        const next = rail.slice(i + 1).find((x) => !x.bead);
        const nat = rail[i].y;
        const top = prevKnot != null ? prevKnot + 16 : nat;     // sát dưới nút trên
        const bot = next ? Math.max(top, next.y - 16) : nat;    // sát trên nút dưới
        beads.push({ el: rail[i].el, nat, top, bot });
      }
      beadsRef.current = beads;
      ulTopRef.current = box.top + window.scrollY;
      applyBeads();
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(ul);
    return () => ro.disconnect();
  }, [items]);

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

  const hasRopes = ropes.length > 0;
  return (
    <section class="cust-feed">
      <div class="row space cf-head">
        <b class="cf-title"><Icon name="clipboard" size={16} /> Đơn & thanh toán {total > 0 ? <span class="muted small">({total})</span> : null}</b>
        <a class="btn small" href={`#/khach/${encodeURIComponent(ckey)}/lich`} title="Lịch biến động">
          <Icon name="calendar" size={15} /> Lịch
        </a>
      </div>

      {loading && !items.length && <SkeletonList rows={4} />}
      <div class={"cf-body" + (hasRopes ? " has-ropes" : "") + (items.length ? " has-items" : "")}>
        {/* dây cong nối payment ↔ đơn: dưới-trái card trên → vòng lề trái → trên-trái card dưới */}
        {(hasRopes || debtSegs.length > 0) && (
          <svg class="feed-ropes" aria-hidden="true">
            {debtSegs.map((s, i) => (
              <line key={`d${i}`} class={`dl-${s.st}`} x1={s.x} x2={s.x} y1={s.y1} y2={s.y2} />
            ))}
            {repZeros.map((z, i) => (
              <g key={`z${i}`} class="rep0">
                <circle cx={z.x} cy={z.y} r="4" />
                <text x={z.x - 9.5} y={z.y}>{z.t}</text>
              </g>
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
          {(() => {
            // đếm số item mỗi ngày (trong phần đã tải) cho header
            const dayCount = new Map<string, number>();
            for (const it of items) { const k = dayOf(it); dayCount.set(k, (dayCount.get(k) || 0) + 1); }
            return items.flatMap((it, i) => {
              const nodes = [];
              // dòng lưu ý tại điểm vượt mốc 6/7/2026 (item đầu tiên CŨ hơn mốc)
              if (it.ts < DEBT_FEATURE_TS && (i === 0 || items[i - 1].ts >= DEBT_FEATURE_TS))
                nodes.push(<li key={`note-${i}`} class="feed-note">{DEBT_NOTE_TEXT}</li>);
              const d = i > 0 ? gapDays(items[i - 1].ts, it.ts) : 0;
              if (d >= 2) nodes.push(gapSpacer(d, `gap-${i}`));
              // header NGÀY dạng divider phẳng — sau khe, trước item đầu của ngày
              const day = dayOf(it);
              if (i === 0 || dayOf(items[i - 1]) !== day) {
                nodes.push(
                  <li key={`day-${day}-${i}`} class="feed-day-li">
                    <div class="order-day-head">{orderDayLabel(day)} <span class="muted small">({dayCount.get(day)})</span></div>
                  </li>
                );
              }
              nodes.push(renderFeedItem(it, { openThumb, jumpToOrder }));
              return nodes;
            });
          })()}
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
