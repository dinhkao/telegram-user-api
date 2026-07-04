// Lịch giao (#/lich) — lưới tháng 7 cột, chấm số đơn theo ngày giao; chạm 1 ngày →
// list đơn giao ngày đó. Data: GET /api/orders/delivery?month=YYYY-MM (rows compact).
import { useEffect, useState } from "preact/hooks";
import { getDeliveryOrders } from "../api";
import { CompactOrderCard } from "../detail/CompactOrderCard";
import { Loading } from "../ui/states";

const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]; // tuần bắt đầu Thứ 2
const pad = (n: number) => String(n).padStart(2, "0");
const iso = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;

export function DeliveryCalendar() {
  const now = new Date();
  const todayIso = iso(now.getFullYear(), now.getMonth(), now.getDate());
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() }); // m: 0-based
  const [byDay, setByDay] = useState<Record<string, any[]>>({});
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState(todayIso);

  const monthStr = `${ym.y}-${pad(ym.m + 1)}`;
  useEffect(() => {
    let alive = true;
    setLoading(true);
    getDeliveryOrders(monthStr)
      .then(({ orders }) => {
        if (!alive) return;
        const g: Record<string, any[]> = {};
        for (const o of orders) {
          const d = (o.ngay_giao || "").slice(0, 10);
          if (d) (g[d] = g[d] || []).push(o);
        }
        setByDay(g);
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [monthStr]);

  const daysInMonth = new Date(ym.y, ym.m + 1, 0).getDate();
  const firstOffset = (new Date(ym.y, ym.m, 1).getDay() + 6) % 7; // ô trống đầu (T2 = 0)
  const cells: (number | null)[] = [
    ...Array(firstOffset).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  const shiftMonth = (delta: number) =>
    setYm(({ y, m }) => {
      const t = m + delta;
      return { y: y + Math.floor(t / 12), m: ((t % 12) + 12) % 12 };
    });

  const selOrders = byDay[sel] || [];
  const [, selM, selD] = sel.split("-");
  const monthTotal = Object.values(byDay).reduce((s, a) => s + a.length, 0);

  return (
    <div class="cal">
      <div class="cal-head">
        <button class="btn small" title="Tháng trước" onClick={() => shiftMonth(-1)}>‹</button>
        <b>Tháng {ym.m + 1} / {ym.y}{monthTotal ? <span class="muted small"> · {monthTotal} đơn</span> : null}</b>
        <button class="btn small" title="Tháng sau" onClick={() => shiftMonth(1)}>›</button>
      </div>

      <div class="cal-grid cal-wd">
        {WEEKDAYS.map((w) => <span class="cal-wd-cell" key={w}>{w}</span>)}
      </div>
      <div class="cal-grid">
        {cells.map((d, i) => {
          if (d === null) return <span class="cal-cell empty" key={`e${i}`} />;
          const ds = iso(ym.y, ym.m, d);
          const dayOrders = byDay[ds] || [];
          const n = dayOrders.length;
          const cls = ["cal-cell", ds === sel ? "sel" : "", ds === todayIso ? "today" : "", n ? "has" : ""].filter(Boolean).join(" ");
          return (
            <button class={cls} key={ds} onClick={() => setSel(ds)}>
              <span class="cal-d">{d}</span>
              {n > 0 && (
                <span class="cal-names">
                  {dayOrders.slice(0, 2).map((o) => (
                    <span class="cal-nm" key={o.thread_id}>{o.customer || o.topic_name || `#${o.thread_id}`}</span>
                  ))}
                  {n > 2 && <span class="cal-more">+{n - 2}</span>}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div class="cal-day-head">
        🚚 Ngày {selD}/{selM}{sel === todayIso ? " (hôm nay)" : ""}{selOrders.length ? ` · ${selOrders.length} đơn` : ""}
      </div>
      {loading ? (
        <Loading />
      ) : selOrders.length ? (
        <ul class="order-list">
          {selOrders.map((o) => <li key={o.thread_id}><CompactOrderCard o={o} /></li>)}
        </ul>
      ) : (
        <p class="muted small">Không có đơn giao ngày này.</p>
      )}
    </div>
  );
}
