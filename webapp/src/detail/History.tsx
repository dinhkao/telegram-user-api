// Lịch sử thao tác dùng chung — GET {base}/history (từ audit_events). base vd
// /api/order/{id} hoặc /api/media/production|box/{id}. Tự cập nhật realtime.
import { useEffect, useState } from "preact/hooks";
import { getJSON, mediaImageUrl } from "../api";
import { fmtTime } from "../format";
import { onRealtime, eventMatchesBase } from "../realtime";

// Cuộn tới ảnh trong khối Ảnh + nháy sáng (tái dùng cơ chế deep-link)
function focusImage(id: number) {
  const el = document.getElementById(`image-${id}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("flash-target");
  setTimeout(() => el.classList.remove("flash-target"), 2400);
}

export function History({ base }: { base: string }) {
  const [items, setItems] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);

  const load = () =>
    getJSON(`${base}/history`, { cache: false })
      .then((r) => { setItems(r.history || []); setLoaded(true); })
      .catch(() => {});

  useEffect(() => { load(); }, [base]);

  // Realtime: thao tác mới trên CÙNG thực thể → tải lại lịch sử (đợi audit ghi xong)
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (eventMatchesBase(base, e)) { clearTimeout(t); t = setTimeout(load, 500); }
    });
    return () => { off(); clearTimeout(t); };
  }, [base]);

  return (
    <div class="card">
      <b>🕘 Lịch sử thao tác</b>
      {items.length ? (
        <ul class="hist">
          {items.map((h, i) => (
            <li key={`${h.ts}-${h.action}-${h.image_id ?? h.detail ?? i}`} class={h.ok === false ? "hist-fail" : ""}>
              <div class="hist-row">
                <div>
                  <div>
                    <b>{h.action}</b>{h.detail ? <span> — {h.detail}</span> : null}
                    {h.ok === false ? <span class="owe"> ✗</span> : null}
                  </div>
                  {Array.isArray(h.changes) && h.changes.length > 0 ? (
                    <ul class="hist-changes">
                      {h.changes.map((c: any, ci: number) => (
                        <li key={ci}>
                          <span class="hc-label">{c.label}:</span>{" "}
                          {c.old ? <span class="hc-old">{c.old}</span> : null}
                          {c.old && c.new ? <span class="hc-arrow"> → </span> : null}
                          {c.new ? <span class="hc-new">{c.new}</span> : null}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <div class="muted small">{h.actor || "?"} · {fmtTime(h.ts)}</div>
                </div>
                {h.image_id ? (
                  <img class="hist-thumb" src={mediaImageUrl(base, h.image_id, "thumb")} loading="lazy" alt="" onClick={() => focusImage(h.image_id)} />
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
