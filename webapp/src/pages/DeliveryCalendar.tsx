// Lịch giao (#/lich) — DÙNG CHUNG ScrollCalendar (cũ→mới, mở ở đáy, lazy 2
// chiều): chấm ĐỎ = đơn CHƯA giao, XANH = đã giao, đúng số lượng. Bấm ngày →
// popup list đơn giao ngày đó (CompactOrderCard). Toggle ẩn đơn đã giao.
// Data: GET /api/orders/delivery?days=1 (đếm) + ?day=YYYY-MM-DD (chi tiết).
import { useEffect, useState } from "preact/hooks";
import { getJSON } from "../api";
import { ScrollCalendar, type CalDays } from "../detail/ScrollCalendar";
import { CompactOrderCard } from "../detail/CompactOrderCard";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { EmptyState } from "../ui/states";

const _WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const dayLabel = (d: string) =>
  `${_WD[(new Date(d).getDay() + 6) % 7]} · ${d.slice(8)}/${d.slice(5, 7)}/${d.slice(0, 4)}`;

export function DeliveryCalendar() {
  const [raw, setRaw] = useState<{ d: string; pending: number; done: number }[]>([]);
  const [hideDelivered, setHideDelivered] = useState(true);   // mặc định ẩn đơn đã giao

  const load = () =>
    getJSON("/api/orders/delivery?days=1", { cache: false })
      .then((r) => setRaw(r.days || []))
      .catch(() => {});
  useEffect(() => { load(); }, []);

  // Realtime: đặt/đổi ngày giao, đánh dấu giao… → tải lại đếm
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "order_changed" || e.type === "orders_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(load, 400);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  // chấm đỏ = chưa giao; xanh = đã giao (ẩn nếu bật toggle)
  const days: CalDays = new Map(
    raw.map((x) => [x.d, { o: x.pending, p: hideDelivered ? 0 : x.done }]),
  );

  // popup đơn giao 1 ngày
  const [pick, setPick] = useState<string | null>(null);
  const [items, setItems] = useState<any[] | null>(null);
  const openDay = (d: string) => {
    setPick(d);
    setItems(null);
    getJSON(`/api/orders/delivery?day=${encodeURIComponent(d)}`, { cache: false })
      .then((r) => setItems(r.orders || []))
      .catch(() => setItems([]));
  };
  const closeDay = () => { setPick(null); setItems(null); };
  useScrollLock(!!pick);
  usePopupBack(!!pick, closeDay);

  const shown = (items || []).filter((o) => !hideDelivered || !o.giao_done);
  return (
    <div class="cal">
      <div class="prod-detail-head">
        <div class="prod-sp"><Icon name="truck" size={18} /> Lịch giao</div>
      </div>
      <label class="cal-toggle">
        <input type="checkbox" checked={hideDelivered} onChange={(e: any) => setHideDelivered(e.target.checked)} />
        <span>Ẩn đơn đã giao rồi</span>
      </label>

      <ScrollCalendar days={days} legend={{ o: "chưa giao", p: "đã giao" }} onPick={openDay} />

      {pick && (
        <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) closeDay(); }}>
          <div class="modal-sheet cc-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="truck" size={16} /> Giao {dayLabel(pick)}
              {items && <span class="muted small"> · {shown.length} đơn</span>}
              <button class="link-btn cc-x" onClick={closeDay}><Icon name="close" size={18} /></button>
            </div>
            {items == null ? (
              <p class="muted small">Đang tải…</p>
            ) : shown.length ? (
              <ul class="order-list cc-list">
                {shown.map((o) => <li key={o.thread_id}><CompactOrderCard o={o} /></li>)}
              </ul>
            ) : (
              <EmptyState>Không có đơn giao ngày này</EmptyState>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
