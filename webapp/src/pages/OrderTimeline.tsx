// Timeline biến động 1 ĐƠN HÀNG (#/order/:id/timeline). Đời của đơn: tạo → HĐ
// KiotViet → xuất kho từng thùng → soạn/giao/nộp/nhận → từng lần thu tiền, kèm
// RAIL TIỀN CÒN PHẢI THU chạy theo (chấm trượt như timeline thùng). Mọi thứ được
// nhắc (thùng/SP/khách/phiếu) là LINK. Data: getOrderTimeline.
import { useEffect, useRef, useState } from "preact/hooks";
import { getOrderTimeline, soVN, type OrderTimeline as OT, type OrderTLItem } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState, LoadingInline } from "../ui/states";
import { dayKeyOf, orderDayLabel } from "../detail/OrderCards";

const GROUP_SEC = 300;
const GAP_PXPS = 0.0333, GAP_MAX = 4000;
const MIN_JUNC = 34, SLIDE_M = 15;
const LAZY_INITIAL = 30, LAZY_BATCH = 30;
const hm = (v?: string) => (fmtDateTimeVN(v || "").match(/\d{2}:\d{2}/) || [""])[0];
function gapLabel(sec: number): string {
  const d = sec / 86400;
  if (d >= 60) return `${Math.round(d / 30)} tháng`;
  if (d >= 14) return `${Math.round(d / 7)} tuần`;
  if (d >= 1) return `${Math.round(d)} ngày`;
  const h = sec / 3600;
  if (h >= 1) return `${Math.round(h)} giờ`;
  return `${Math.max(1, Math.round(sec / 60))} phút`;
}

function EventRow({ it, threadId }: { it: OrderTLItem; threadId: string }) {
  const parts = (it.parts || []).map((p, pi) =>
    p.href ? <a key={pi} class="pt-inl" href={p.href}>{p.t}</a> : <span key={pi}>{p.t}</span>);
  return (
    <li class="pt-item">
      <div class="pt-line">
        <span class="pt-time">{hm(it.at)}</span>
        <span class={"pt-tag " + it.dir}>{it.dir === "in" ? "+" : it.dir === "out" ? "−" : "•"}</span>
        <span class="pt-line-txt">
          {it.actor && it.actor !== "?" ? <><b class="pt-who">{it.actor}</b> </> : null}
          <b>{it.label}</b>
          {it.kind === "payment" && it.amount ? <> <b class="d-ok">−{soVN(it.amount)}đ</b></> : null}
          {parts.length ? <> — {parts}</> : null}
          {it.image_id ? (
            <> · <a class="pt-inl" href={`#/order/${threadId}?focus=image:${it.image_id}`}>xem ảnh →</a></>
          ) : null}
          {Array.isArray(it.changes) && it.changes.length > 0 ? (
            <ul class="hist-changes">
              {it.changes.map((c: any, ci: number) => (
                <li key={ci}>
                  <span class="hc-label">{c.label}:</span>{" "}
                  {c.old ? <span class="hc-old">{c.old}</span> : null}
                  {c.old && c.new ? <span class="hc-arrow"> → </span> : null}
                  {c.new ? <span class="hc-new">{c.new}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </span>
      </div>
      <span class="pt-rail" />
    </li>
  );
}

function Junction({ height, label, amount }: { height: number; label: string | null; amount?: number | null }) {
  return (
    <li class="pt-junc" style={height ? { height: `${height}px` } : undefined}>
      <span class="pt-junc-mid">
        {label && <span class="pt-gaplbl pt-slide"><span class="fg-label">· {label} ·</span></span>}
      </span>
      <span class="pt-rail">
        <span class="pt-bead pt-slide">
          {amount != null && <span class="pt-dot-amt">{soVN(amount)}</span>}
          <span class="pt-dot pt-dot-static" />
        </span>
      </span>
    </li>
  );
}

export function OrderTimeline({ threadId }: { threadId: string }) {
  const [d, setD] = useState<OT | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const listRef = useRef<HTMLUListElement>(null);
  const [shown, setShown] = useState(LAZY_INITIAL);
  const moreRef = useRef<HTMLLIElement>(null);
  useEffect(() => { setShown(LAZY_INITIAL); }, [d]);
  useEffect(() => {
    const el = moreRef.current;
    const n = d?.items.length || 0;
    if (!el || shown >= n) return;
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) setShown((s) => Math.min(n, s + LAZY_BATCH));
    }, { rootMargin: "800px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [shown, d]);

  // chấm tiền trượt theo cuộn (same cơ chế BoxTimeline)
  useEffect(() => {
    const apply = () => {
      const juncs = listRef.current?.querySelectorAll<HTMLElement>(".pt-junc");
      if (!juncs) return;
      const pin = window.innerHeight * 0.45;
      juncs.forEach((j) => {
        const r = j.getBoundingClientRect();
        const off = r.height <= SLIDE_M * 2 ? r.height / 2 : Math.min(Math.max(pin - r.top, SLIDE_M), r.height - SLIDE_M);
        j.querySelectorAll<HTMLElement>(".pt-slide").forEach((el) => { el.style.top = `${off}px`; });
      });
    };
    let raf = 0, running = false, lastY = -1, idle = 0;
    const tick = () => {
      const y = window.scrollY;
      if (y !== lastY) { lastY = y; idle = 0; apply(); }
      else if (++idle > 20) { running = false; return; }
      raf = requestAnimationFrame(tick);
    };
    const onScroll = () => { if (!running) { running = true; idle = 0; raf = requestAnimationFrame(tick); } };
    window.addEventListener("scroll", onScroll, { passive: true });
    const t = setTimeout(apply, 60);
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); clearTimeout(t); };
  }, [d, shown]);

  const load = () => {
    getOrderTimeline(threadId)
      .then((r) => { if (!r) setErr("Không tìm thấy đơn"); else { setD(r); setErr(""); } })
      .catch((e: any) => setErr(e?.message || "Lỗi tải timeline"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [threadId]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e: any) => {
      if (e.type === "order_changed" && String(e.thread_id) === String(threadId)) {
        clearTimeout(t); t = setTimeout(load, 500);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [threadId]);

  if (loading && !d) return <Loading />;
  if (err || !d) return <ErrorState msg={err || "Không tìm thấy"} onRetry={load} />;

  const items = d.items;
  const rows: any[] = [];
  if (items.length) {
    rows.push(<li key="d-top" class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(items[0].at))}</div></li>);
    rows.push(<Junction key="j-top" height={MIN_JUNC} label={null} amount={d.order.remaining} />);
  }
  const lim = Math.min(shown, items.length);
  for (let i = 0; i < lim; i++) {
    const it = items[i];
    rows.push(<EventRow key={`e-${i}`} it={it} threadId={threadId} />);
    const older = items[i + 1];
    if (older && i + 1 < lim) {
      const dsec = Math.max(0, it.ts - older.ts);
      const cross = dayKeyOf(it.at) !== dayKeyOf(older.at);
      if (dsec > GROUP_SEC) {
        const gh = Math.max(MIN_JUNC, cross ? 0 : Math.round(Math.min(dsec * GAP_PXPS, GAP_MAX)));
        rows.push(<Junction key={`j-${i}`} height={gh} label={cross ? null : gapLabel(dsec)} amount={older.remaining} />);
      }
      if (cross) rows.push(<li key={`d-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(older.at))}</div></li>);
    }
  }
  if (lim < items.length) rows.push(<li key="more" ref={moreRef} class="pt-more"><span class="muted small"><LoadingInline label="Đang tải thêm…" /></span></li>);

  const o = d.order;
  return (
    <div class="place-tl">
      <div class="prod-detail-head">
        <BackLink fallback={`#/order/${threadId}`} />
        <div>
          <div class="prod-sp big"><Icon name="receipt" size={17} /> {o.text || `Đơn #${o.thread_id}`}</div>
          <div class="prod-date muted">
            Timeline biến động đơn
            {o.customer_name ? <> · <a class="pt-inl" href={`#/khach/${o.customer_key}`}>{o.customer_name}</a></> : null}
            {o.kv_code ? <> · {o.kv_code}</> : null}
          </div>
        </div>
      </div>

      <div class="pt-head card">
        <div>
          <div class={"pt-total-big" + (o.remaining > 0 ? "" : " zero")}>{soVN(o.remaining)}đ</div>
          <div class="muted small">còn phải thu · tổng {soVN(o.total)}đ · đã thu {soVN(o.paid)}đ</div>
        </div>
        <span class="muted small">{items.length} biến động{d.truncated ? " (mới nhất)" : ""}</span>
      </div>

      {items.length === 0 ? (
        <EmptyState>Đơn này chưa có biến động nào được ghi.</EmptyState>
      ) : (
        <ul class="pt-list" ref={listRef}>{rows}</ul>
      )}
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {items.length} biến động gần nhất.</div>}
    </div>
  );
}
