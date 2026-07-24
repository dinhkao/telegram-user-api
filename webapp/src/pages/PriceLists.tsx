// Danh sách bảng giá chung (#/bang-gia) — GET /api/price-lists. Bấm 1 bảng →
// chi tiết (#/bang-gia/:id) để sửa giá + xem khách dùng + lịch sử đổi giá.
import { useEffect, useState } from "preact/hooks";
import { getPriceLists, type PriceListSummary } from "../api";
import { onRealtime } from "../realtime";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";

export function PriceLists() {
  const [lists, setLists] = useState<PriceListSummary[] | null>(null);
  const [err, setErr] = useState("");

  const reload = () => getPriceLists().then((r) => { setLists(r); setErr(""); }).catch((e) => setErr(e.message));

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
      <PageHead fallback="#/home" title={<><Icon name="wallet" size={18} /> Bảng giá chung</>} />
      {err ? (
        <ErrorState msg={err} onRetry={reload} />
      ) : !lists ? (
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
