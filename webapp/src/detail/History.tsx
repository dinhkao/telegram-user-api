// Lịch sử thao tác của đơn — GET /api/order/{id}/history (từ audit_events).
// Luôn hiện + tự cập nhật realtime khi đơn có thao tác mới.
import { useEffect, useState } from "preact/hooks";
import { getJSON, orderImageUrl } from "../api";
import { fmtTime } from "../format";
import { onRealtime } from "../realtime";

// Cuộn tới ảnh trong khối Ảnh + nháy sáng (tái dùng cơ chế deep-link)
function focusImage(id: number) {
  const el = document.getElementById(`image-${id}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("flash-target");
  setTimeout(() => el.classList.remove("flash-target"), 2400);
}

export function History({ threadId }: { threadId: string }) {
  const [items, setItems] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);

  const load = () =>
    getJSON(`/api/order/${threadId}/history`, { cache: false })
      .then((r) => { setItems(r.history || []); setLoaded(true); })
      .catch(() => {});

  useEffect(() => { load(); }, [threadId]);

  // Realtime: đơn có thao tác mới (hoặc nối lại) → tải lại lịch sử (debounce nhỏ;
  // đợi audit ghi xong sau khi handler trả về).
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if ((e.type === "order_changed" && e.thread_id === String(threadId)) || e.type === "resync") {
        clearTimeout(t);
        t = setTimeout(load, 500);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [threadId]);

  return (
    <div class="card">
      <b>🕘 Lịch sử thao tác</b>
      {items.length ? (
        <ul class="hist">
          {items.map((h, i) => (
            <li key={i} class={h.ok === false ? "hist-fail" : ""}>
              <div class="hist-row">
                <div>
                  <div>
                    <b>{h.action}</b>{h.detail ? <span> — {h.detail}</span> : null}
                    {h.ok === false ? <span class="owe"> ✗</span> : null}
                  </div>
                  <div class="muted small">{h.actor || "?"} · {fmtTime(h.ts)}</div>
                </div>
                {h.image_id ? (
                  <img class="hist-thumb" src={orderImageUrl(threadId, h.image_id, "thumb")} loading="lazy" alt="" onClick={() => focusImage(h.image_id)} />
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p class="muted small">{loaded ? "Chưa có thao tác nào được ghi." : "Đang tải…"}</p>
      )}
    </div>
  );
}
