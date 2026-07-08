// Lịch tháng biến động của khách (trang chi tiết khách, đổi qua lại với feed).
// Ngày có biến động: chấm ĐỎ (có đơn) / XANH (có phiếu thu). Bấm ngày → popup
// liệt kê biến động ngày đó — TÁI DÙNG renderItem của CustomerFeed (card y hệt).
// Data: GET /api/customers/{key}/feed?days=1 (đếm) + ?day=YYYY-MM-DD (chi tiết).
import { useEffect, useState } from "preact/hooks";
import { getCustomerFeedDays, getCustomerFeedDay, type CustFeedItem } from "../api";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";
import { EmptyState } from "../ui/states";

const _WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const _MONTH = (y: number, m: number) => `Tháng ${m + 1}/${y}`;
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
  const [ym, setYm] = useState<{ y: number; m: number }>({ y: now.getFullYear(), m: now.getMonth() });
  const [pick, setPick] = useState<string | null>(null);          // ngày đang mở popup
  const [dayItems, setDayItems] = useState<CustFeedItem[] | null>(null);

  useEffect(() => {
    getCustomerFeedDays(ckey)
      .then((list) => setDays(new Map(list.map((x) => [x.d, { o: x.o, p: x.p }]))))
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

  const shift = (dm: number) => setYm(({ y, m }) => {
    const t = new Date(y, m + dm, 1);
    return { y: t.getFullYear(), m: t.getMonth() };
  });

  const todayKey = keyOf(now.getFullYear(), now.getMonth(), now.getDate());
  const pickLabel = pick ? `${_WD[(new Date(pick).getDay() + 6) % 7]} · ${pick.slice(8)}/${pick.slice(5, 7)}/${pick.slice(0, 4)}` : "";

  return (
    <div class="cust-cal">
      <div class="cc-nav">
        <button class="btn small" onClick={() => shift(-1)}><Icon name="back" size={16} /></button>
        <b class="cc-month">{_MONTH(ym.y, ym.m)}</b>
        <button class="btn small" onClick={() => shift(1)}><Icon name="chevronRight" size={16} /></button>
      </div>
      <div class="cc-grid cc-head">
        {_WD.map((w) => <span key={w} class="cc-wd">{w}</span>)}
      </div>
      <div class="cc-grid">
        {monthCells(ym.y, ym.m).map((d, i) => {
          if (d == null) return <span key={`e${i}`} class="cc-cell empty" />;
          const k = keyOf(ym.y, ym.m, d);
          const c = days.get(k);
          return (
            <button key={k} class={"cc-cell" + (c ? " has" : "") + (k === todayKey ? " today" : "")}
              disabled={!c} onClick={() => openDay(k)}
              title={c ? `${c.o ? `${c.o} đơn` : ""}${c.o && c.p ? " · " : ""}${c.p ? `${c.p} phiếu thu` : ""}` : undefined}>
              <span class="cc-d">{d}</span>
              {c && (
                <span class="cc-dots">
                  {c.o > 0 && <span class="cc-dot o" />}
                  {c.p > 0 && <span class="cc-dot p" />}
                </span>
              )}
            </button>
          );
        })}
      </div>
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
