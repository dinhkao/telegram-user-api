// Trang LỊCH biến động của 1 khách (#/khach/:key/lich) — ScrollCalendar dùng
// chung (cũ→mới, mở ở đáy, lazy 2 chiều). Bấm ngày → popup liệt kê biến động
// ngày đó, card tái dùng renderFeedItem (y hệt feed, kèm rail nợ).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getCustomer, getCustomerFeedDays, getCustomerFeedDay, listOrderImages,
  type CustFeedItem, type OrderImage,
} from "../api";
import { ScrollCalendar, type CalDays } from "../detail/ScrollCalendar";
import { renderFeedItem } from "../detail/CustomerFeed";
import { PhotoViewer } from "../detail/PhotoViewer";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";
import { EmptyState } from "../ui/states";
import type { OrderRow } from "../detail/OrderCards";

const _WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const dayLabel = (d: string) =>
  `${_WD[(new Date(d).getDay() + 6) % 7]} · ${d.slice(8)}/${d.slice(5, 7)}/${d.slice(0, 4)}`;

export function CustomerCalendarPage({ ckey }: { ckey: string }) {
  const [name, setName] = useState("");
  const [days, setDays] = useState<CalDays>(new Map());
  useEffect(() => {
    getCustomer(ckey).then((c) => setName(c.name || "")).catch(() => {});
    getCustomerFeedDays(ckey)
      .then((list) => setDays(new Map(list.map((x) => [x.d, { o: x.o, p: x.p }]))))
      .catch(() => {});
  }, [ckey]);

  // popup biến động 1 ngày
  const [pick, setPick] = useState<string | null>(null);
  const [items, setItems] = useState<CustFeedItem[] | null>(null);
  const openDay = (d: string) => {
    setPick(d);
    setItems(null);
    getCustomerFeedDay(ckey, d).then(setItems).catch(() => setItems([]));
  };
  const closeDay = () => { setPick(null); setItems(null); };
  useScrollLock(!!pick);
  usePopupBack(!!pick, closeDay);

  // PhotoViewer khi bấm thumb trong popup (giống feed)
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
  const renderItem = (it: CustFeedItem) =>
    renderFeedItem(it, { openThumb, jumpToOrder: (tid) => { window.location.hash = `#/order/${tid}`; } });

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <BackLink fallback={`#/khach/${encodeURIComponent(ckey)}`} />
        <div>
          <div class="prod-sp"><Icon name="calendar" size={18} /> Lịch biến động</div>
          <div class="muted small">{name || ckey}</div>
        </div>
      </div>
      <ScrollCalendar days={days} legend={{ o: "đơn hàng", p: "thanh toán" }} onPick={openDay} />

      {pick && (
        <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) closeDay(); }}>
          <div class="modal-sheet cc-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="calendar" size={16} /> {dayLabel(pick)}
              <button class="link-btn cc-x" onClick={closeDay}><Icon name="close" size={18} /></button>
            </div>
            {items == null ? (
              <p class="muted small">Đang tải…</p>
            ) : items.length ? (
              <ul class="order-list cc-list">{items.map(renderItem)}</ul>
            ) : (
              <EmptyState>Không có biến động ngày này</EmptyState>
            )}
          </div>
        </div>
      )}
      {viewer && (
        <PhotoViewer images={viewer.images} start={viewer.start} base={`/api/order/${viewer.threadId}`} editable
          onKindChange={(id, kind) => setViewer((v: any) => v && ({ ...v, images: v.images.map((x: any) => (x.id === id ? { ...x, kind } : x)) }))}
          onClose={() => setViewer(null)} />
      )}
    </div>
  );
}
