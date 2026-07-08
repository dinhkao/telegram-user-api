// Lịch tháng biến động của khách (TRANG RIÊNG #/khach/:key/lich) — tháng xếp
// CŨ→MỚI, mở sẵn ở đáy (tháng hiện tại), cuộn LÊN là về quá khứ. LAZY 2 CHIỀU:
// cửa sổ tháng render mở rộng dần bằng sentinel trên/dưới (bù scroll khi prepend).
// Ngày có biến động: chấm ĐỎ (có đơn) / XANH (có phiếu thu). Bấm ngày → popup
// liệt kê biến động ngày đó — TÁI DÙNG renderItem của CustomerFeed (card y hệt).
// Data: GET /api/customers/{key}/feed?days=1 (đếm) + ?day=YYYY-MM-DD (chi tiết).
import { useEffect, useRef, useState } from "preact/hooks";
import { getCustomerFeedDays, getCustomerFeedDay, type CustFeedItem } from "../api";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";
import { EmptyState } from "../ui/states";

const _WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const _MONTH = (y: number, m: number) => `Tháng ${m + 1}/${y}`;

/** Dãy tháng (CŨ → MỚI — đúng chiều thời gian: cuộn lên là về quá khứ). */
function monthRange(days: Map<string, unknown>, now: Date): { y: number; m: number }[] {
  let earliest = `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
  for (const k of days.keys()) {
    const ym = k.slice(0, 7);
    if (ym < earliest) earliest = ym;
  }
  const out: { y: number; m: number }[] = [];
  let y = now.getFullYear(), m = now.getMonth();
  for (let i = 0; i < 120; i++) {   // trần 10 năm — chống vòng lặp dữ liệu hỏng
    out.push({ y, m });
    if (`${y}-${pad(m + 1)}` <= earliest) break;
    m -= 1;
    if (m < 0) { m = 11; y -= 1; }
  }
  return out.reverse();   // cũ nhất trên cùng → tháng hiện tại dưới cùng
}
const pad = (n: number) => String(n).padStart(2, "0");
const keyOf = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;

/** Các ô của 1 tháng (Thứ 2 đầu tuần): null = ô trống đầu/cuối lưới. */
function monthCells(y: number, m: number): (number | null)[] {
  const first = new Date(y, m, 1);
  const lead = (first.getDay() + 6) % 7;   // CN=0 → 6; T2=1 → 0
  const days = new Date(y, m + 1, 0).getDate();
  const cells: (number | null)[] = Array(lead).fill(null);
  for (let d = 1; d <= days; d++) cells.push(d);
  while (cells.length % 7) cells.push(null);
  return cells;
}

export function CustomerCalendar({ ckey, renderItem }: {
  ckey: string;
  /** tái dùng renderItem của CustomerFeed — card trong popup y hệt ngoài feed */
  renderItem: (it: CustFeedItem) => any;
}) {
  const [days, setDays] = useState<Map<string, { o: number; p: number }>>(new Map());
  const now = new Date();
  const [pick, setPick] = useState<string | null>(null);          // ngày đang mở popup
  const [dayItems, setDayItems] = useState<CustFeedItem[] | null>(null);
  // LAZY 2 CHIỀU: chỉ render cửa sổ [start..end] của dãy tháng; sentinel trên/dưới nới dần
  const [win, setWin] = useState<{ start: number; end: number } | null>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const botRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getCustomerFeedDays(ckey)
      .then((list) => {
        const map = new Map(list.map((x) => [x.d, { o: x.o, p: x.p }] as const));
        setDays(map);
        const n = monthRange(map, new Date()).length;
        setWin({ start: Math.max(0, n - 4), end: n - 1 });   // mở 4 tháng gần nhất
        // mở tại ĐÁY (tháng hiện tại) — cuộn LÊN là lùi về quá khứ
        requestAnimationFrame(() =>
          window.scrollTo(0, document.documentElement.scrollHeight));
      })
      .catch(() => {});
  }, [ckey]);

  const openDay = (k: string) => {
    setPick(k);
    setDayItems(null);
    getCustomerFeedDay(ckey, k).then(setDayItems).catch(() => setDayItems([]));
  };
  const closeDay = () => { setPick(null); setDayItems(null); };
  useScrollLock(!!pick);
  usePopupBack(!!pick, closeDay);

  // nới cửa sổ: LÊN (prepend tháng cũ — BÙ scroll giữ nguyên khung nhìn) / XUỐNG
  const monthsAll = monthRange(days, now);
  useEffect(() => {
    if (!win) return;
    const io = new IntersectionObserver((ents) => {
      for (const en of ents) {
        if (!en.isIntersecting) continue;
        if (en.target === topRef.current && win.start > 0) {
          const before = document.documentElement.scrollHeight;
          setWin((w) => w && ({ ...w, start: Math.max(0, w.start - 4) }));
          requestAnimationFrame(() =>
            window.scrollBy(0, document.documentElement.scrollHeight - before));
        } else if (en.target === botRef.current && win.end < monthsAll.length - 1) {
          setWin((w) => w && ({ ...w, end: Math.min(monthsAll.length - 1, w.end + 4) }));
        }
      }
    }, { rootMargin: "300px 0px" });
    if (topRef.current) io.observe(topRef.current);
    if (botRef.current) io.observe(botRef.current);
    return () => io.disconnect();
  }, [win?.start, win?.end, monthsAll.length]);

  const todayKey = keyOf(now.getFullYear(), now.getMonth(), now.getDate());
  const pickLabel = pick ? `${_WD[(new Date(pick).getDay() + 6) % 7]} · ${pick.slice(8)}/${pick.slice(5, 7)}/${pick.slice(0, 4)}` : "";

  return (
    <div class="cust-cal">
      {/* CUỘN DỌC cũ→mới, mở ở đáy; lazy 2 chiều qua sentinel */}
      <div ref={topRef} style="height:1px" />
      {(win ? monthsAll.slice(win.start, win.end + 1) : []).map(({ y, m }) => (
        <div class="cc-block" key={`${y}-${m}`}>
          <div class="cc-month-head"><b class="cc-month">{_MONTH(y, m)}</b></div>
          <div class="cc-grid cc-head">
            {_WD.map((w) => <span key={w} class="cc-wd">{w}</span>)}
          </div>
          <div class="cc-grid">
            {monthCells(y, m).map((d, i) => {
              if (d == null) return <span key={`e${i}`} class="cc-cell empty" />;
              const k = keyOf(y, m, d);
              const c = days.get(k);
              return (
                <button key={k} class={"cc-cell" + (c ? " has" : "") + (k === todayKey ? " today" : "")}
                  disabled={!c} onClick={() => openDay(k)}
                  title={c ? `${c.o ? `${c.o} đơn` : ""}${c.o && c.p ? " · " : ""}${c.p ? `${c.p} phiếu thu` : ""}` : undefined}>
                  <span class="cc-d">{d}</span>
                  {c && (
                    <span class="cc-dots">
                      {Array.from({ length: c.o }, (_, j) => <span key={`o${j}`} class="cc-dot o" />)}
                      {Array.from({ length: c.p }, (_, j) => <span key={`p${j}`} class="cc-dot p" />)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <div ref={botRef} style="height:1px" />
      <div class="cc-legend muted small">
        <span><span class="cc-dot o" /> đơn hàng</span>
        <span><span class="cc-dot p" /> thanh toán</span>
      </div>

      {pick && (
        <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) closeDay(); }}>
          <div class="modal-sheet cc-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="calendar" size={16} /> {pickLabel}
              <button class="link-btn cc-x" onClick={closeDay}><Icon name="close" size={18} /></button>
            </div>
            {dayItems == null ? (
              <p class="muted small">Đang tải…</p>
            ) : dayItems.length ? (
              <ul class="order-list cc-list">{dayItems.map(renderItem)}</ul>
            ) : (
              <EmptyState>Không có biến động ngày này</EmptyState>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
