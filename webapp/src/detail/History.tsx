// Lịch sử thao tác của đơn — GET /api/order/{id}/history (từ audit_events).
// Thu gọn mặc định; bấm "Xem" mới tải (khỏi tốn cho mỗi lần mở đơn).
import { useEffect, useState } from "preact/hooks";
import { getJSON } from "../api";
import { fmtTime } from "../format";

export function History({ threadId }: { threadId: string }) {
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (!open || loaded) return;
    getJSON(`/api/order/${threadId}/history`, { cache: false })
      .then((r) => { setItems(r.history || []); setLoaded(true); })
      .catch(() => {});
  }, [open, threadId, loaded]);

  return (
    <div class="card">
      <div class="row space">
        <b>🕘 Lịch sử thao tác</b>
        <button class="btn small" onClick={() => setOpen((o) => !o)}>{open ? "Ẩn" : "Xem"}</button>
      </div>
      {open && (
        items.length ? (
          <ul class="hist">
            {items.map((h, i) => (
              <li key={i} class={h.ok === false ? "hist-fail" : ""}>
                <div>
                  <b>{h.action}</b>{h.detail ? <span> — {h.detail}</span> : null}
                  {h.ok === false ? <span class="owe"> ✗</span> : null}
                </div>
                <div class="muted small">{h.actor || "?"} · {fmtTime(h.ts)}</div>
              </li>
            ))}
          </ul>
        ) : (
          <p class="muted small">{loaded ? "Chưa có thao tác nào được ghi." : "Đang tải…"}</p>
        )
      )}
    </div>
  );
}
