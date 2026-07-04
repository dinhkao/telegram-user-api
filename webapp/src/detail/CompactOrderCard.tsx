// Thẻ đơn "gọn" tái dùng — ảnh cao full thân + 5 icon trạng thái + giờ, bấm →
// chi tiết đơn. Dùng CSS .order-card.compact chung với dashboard. Dùng ở trang
// chi tiết khách (list đơn của khách). Nhận sẵn 1 order row (shape _build_order_row).
import { orderImageUrl } from "../api";
import { fmtDateTimeVN, fmtRelative, fmtNgayGiao } from "../format";

const TASK_LABELS = ["HĐ", "Soạn", "Giao", "Nộp", "Nhận"];

export function TaskBadges({ o }: { o: any }) {
  const icons = [...(o.task_icons || "")];
  const fallback: boolean[] = [false, o.soan, o.giao, o.nop, o.nhan];
  return (
    <span class="badges">
      {TASK_LABELS.map((label, i) => (
        <span class="tstat" key={label}>
          <span class="tico">{icons[i] || (fallback[i] ? "✅" : "❌")}</span>
          <span class="tlbl">{label}</span>
        </span>
      ))}
    </span>
  );
}

export function CompactOrderCard({ o }: { o: any }) {
  const allIds: number[] = o.thumb_image_ids?.length ? o.thumb_image_ids : (o.thumb_image_id ? [o.thumb_image_id] : []);
  const total = o.image_count ?? allIds.length;
  return (
    <a class="order-card compact" href={`#/order/${o.thread_id}`}>
      {allIds.length > 0 && (
        <span class="card-thumb-wrap compact-thumb">
          <img class="card-thumb card-thumb-tile" src={orderImageUrl(o.thread_id, allIds[0], "thumb")} loading="lazy" alt="" />
          {total > 1 && <span class="thumb-count">+{total - 1}</span>}
        </span>
      )}
      <div class="compact-right">
        <div class="order-text wrap-badges">
          <TaskBadges o={o} />
          <span class="ot-text">{o.text || <span class="muted">(không có nội dung)</span>}</span>
        </div>
        <div class="order-when muted small">
          🕒 {o.created ? <>{fmtDateTimeVN(o.created)} · {fmtRelative(o.created)}</> : o.date}
        </div>
        {o.ngay_giao && <div class="od-deliver">🚚 Giao {fmtNgayGiao(o.ngay_giao)}</div>}
      </div>
    </a>
  );
}
