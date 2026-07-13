// Ai đang giao đơn nào: giao_hang.done nhưng nop_tien chưa done.
import { useCallback, useEffect, useMemo, useState } from "preact/hooks";
import { getJSON, soVN } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { EmptyState, ErrorState, SkeletonList } from "../ui/states";

type DeliveryOrder = {
  thread_id: number; customer: string; total: string; paid: number; remaining: number;
  hd_code?: string; invoice_summary?: { sp: string; sl: number }[];
  delivery_actor: string; delivery_actor_id: string; delivery_since?: string;
};

function money(v: string | number) {
  const n = Number(String(v || 0).replace(/\./g, ""));
  return n ? `${soVN(n)}đ` : "—";
}

function relativeWhen(v?: string) {
  if (!v) return "Không rõ thời gian";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v.slice(0, 16).replace("T", " ");
  const seconds = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (seconds < 60) return "vừa xong";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} ngày trước`;
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function DeliveringOrders() {
  const [orders, setOrders] = useState<DeliveryOrder[] | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setError("");
    getJSON("/api/orders/delivering", { cache: false })
      .then((d) => setOrders(d.orders || []))
      .catch((e) => setError(e.message || "Không tải được dữ liệu"));
  }, []);
  useEffect(() => {
    load();
    return onRealtime((e) => {
      if (e.type === "order_changed" || e.type === "orders_changed" || e.type === "resync") load();
    });
  }, [load]);

  const groups = useMemo(() => {
    const m = new Map<string, DeliveryOrder[]>();
    for (const o of orders || []) {
      const key = o.delivery_actor || "Chưa rõ người giao";
      m.set(key, [...(m.get(key) || []), o]);
    }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], "vi"));
  }, [orders]);

  if (error) return <div class="delivering-page"><ErrorState msg={error} onRetry={load} /></div>;
  if (!orders) return <div class="delivering-page"><SkeletonList rows={4} /></div>;
  return (
    <div class="delivering-page">
      <section class="dl-hero">
        <div><span class="dl-kicker">Đang ở ngoài đường</span><h1>{orders.length} đơn đang giao</h1></div>
        <div class="dl-people"><Icon name="users" size={18} /><b>{groups.length}</b><span>người</span></div>
      </section>
      <p class="dl-rule"><Icon name="info" size={14} /> Đã giao, chưa nộp tiền · không tính đơn hẹn “Chiều lấy tiền” · từ 13/07/2026.</p>
      {!orders.length ? <EmptyState icon="✓">Không có đơn nào đang giao.</EmptyState> : groups.map(([person, list]) => (
        <section class="dl-group" key={person}>
          <header class="dl-group-head">
            <span class="dl-avatar">{person.trim().charAt(0).toUpperCase() || "?"}</span>
            <div><h2>{person}</h2><span>{list.length} đơn đang giữ</span></div>
          </header>
          <div class="dl-list">{list.map((o) => (
            <a class="dl-card" href={`#/order/${o.thread_id}`} key={o.thread_id}>
              <div class="dl-card-top"><b>{o.customer || `Đơn #${o.thread_id}`}</b><span>{money(o.remaining || o.total)}</span></div>
              <div class="dl-products">{(o.invoice_summary || []).map((x) => `${x.sp} ×${soVN(x.sl)}`).join(" · ") || "Chưa có sản phẩm"}</div>
              <div class="dl-meta">
                <span title={o.delivery_since}><Icon name="clock" size={13} /> {relativeWhen(o.delivery_since)}</span>
                <span>{o.hd_code ? `HĐ ${o.hd_code}` : `#${o.thread_id}`}</span>
                <Icon name="chevronRight" size={16} />
              </div>
            </a>
          ))}</div>
        </section>
      ))}
    </div>
  );
}
