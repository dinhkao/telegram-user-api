// Trang lịch sử thao tác TOÀN BỘ (#/lich-su) — gộp mọi đơn/phiếu SX/thùng.
// Data: GET /api/activity?page=N. Mỗi dòng link tới trang chi tiết tương ứng.
import { useEffect, useState } from "preact/hooks";
import { getActivity } from "../api";
import { fmtTime } from "../format";
import { Loading } from "../ui/states";

export function ActivityLog() {
  const [items, setItems] = useState<any[]>([]);
  const [before, setBefore] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async (cursor: number | null) => {
    setLoading(true);
    try {
      const r = await getActivity(cursor);
      setItems((prev) => (cursor == null ? r.items : [...prev, ...r.items]));
      setHasMore(!!r.has_more);
      setBefore(r.next_before ?? null);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(null); }, []);

  return (
    <div>
      <h2 class="page-h">🕘 Lịch sử thao tác</h2>
      {items.length ? (
        <ul class="hist act-log">
          {items.map((h, i) => (
            <li key={i} class={h.ok === false ? "hist-fail" : ""}>
              <a class="act-item" href={h.href || undefined}>
                <div>
                  <div>
                    <span class="act-scope">{h.scope_label}</span> <b>{h.action}</b>
                    {h.detail ? <span> — {h.detail}</span> : null}
                    {h.entity_id ? <span class="muted small"> #{h.entity_id}</span> : null}
                    {h.ok === false ? <span class="owe"> ✗</span> : null}
                  </div>
                  <div class="muted small">{h.actor || "?"} · {fmtTime(h.ts)}</div>
                </div>
                {h.href ? <span class="act-go muted">›</span> : null}
              </a>
            </li>
          ))}
        </ul>
      ) : loading ? (
        <Loading />
      ) : (
        <p class="muted small">Chưa có thao tác nào được ghi.</p>
      )}
      {!loading && hasMore && <button class="btn small wide" onClick={() => load(before)}>Tải thêm</button>}
      {loading && items.length > 0 && <p class="muted center small">Đang tải…</p>}
    </div>
  );
}
