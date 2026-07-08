// Trang LỊCH biến động của 1 khách (#/khach/:key/lich) — tách khỏi trang chi
// tiết. Lịch xếp CŨ→MỚI (mở ở đáy = tháng hiện tại, cuộn lên là về quá khứ),
// lazy 2 chiều. Popup ngày tái dùng renderFeedItem (card + rail nợ y hệt feed).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getCustomer, listOrderImages, type CustFeedItem, type OrderImage } from "../api";
import { CustomerCalendar } from "../detail/CustomerCalendar";
import { renderFeedItem } from "../detail/CustomerFeed";
import { PhotoViewer } from "../detail/PhotoViewer";
import { Icon } from "../ui/Icon";
import type { OrderRow } from "../detail/OrderCards";

export function CustomerCalendarPage({ ckey }: { ckey: string }) {
  const [name, setName] = useState("");
  useEffect(() => { getCustomer(ckey).then((c) => setName(c.name || "")).catch(() => {}); }, [ckey]);

  // PhotoViewer khi bấm thumb trong popup ngày (giống feed)
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
      <CustomerCalendar ckey={ckey} renderItem={renderItem} />
      {viewer && (
        <PhotoViewer images={viewer.images} start={viewer.start} base={`/api/order/${viewer.threadId}`} editable
          onKindChange={(id, kind) => setViewer((v: any) => v && ({ ...v, images: v.images.map((x: any) => (x.id === id ? { ...x, kind } : x)) }))}
          onClose={() => setViewer(null)} />
      )}
    </div>
  );
}
