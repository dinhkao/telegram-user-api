// Danh sách bảng giá chung (#/bang-gia) — GET /api/price-lists. Bấm 1 bảng →
// chi tiết (#/bang-gia/:id) để sửa giá + xem khách dùng + lịch sử đổi giá.
import { useEffect, useState } from "preact/hooks";
import { getPriceLists, type PriceListSummary } from "../api";
import { onRealtime } from "../realtime";
import { Loading, EmptyState } from "../ui/states";

export function PriceLists() {
  const [lists, setLists] = useState<PriceListSummary[] | null>(null);
  const [err, setErr] = useState("");

  const reload = () => getPriceLists().then(setLists).catch((e) => setErr(e.message));

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "price_lists_changed") {
        clearTimeout(t);
        t = setTimeout(reload, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  return (
    <div>
      <h2>💰 Bảng giá chung</h2>
      {err && <p class="error">{err}</p>}
      {!lists ? (
        <Loading />
      ) : !lists.length ? (
        <EmptyState>Chưa có bảng giá chung nào.</EmptyState>
      ) : (
        <ul class="order-list">
          {lists.map((l) => (
            <li key={l.id}>
              <a class="order-card" href={`#/bang-gia/${encodeURIComponent(l.id)}`}>
                <div class="row space">
                  <b>{l.name}</b>
                  <span class="muted small">{l.product_count} SP</span>
                </div>
                <span class="muted small">#{l.id} · sửa giá · khách dùng · lịch sử →</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
