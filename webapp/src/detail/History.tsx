// Lịch sử thao tác dùng chung — GET {base}/history (từ audit_events). base vd
// /api/order/{id} hoặc /api/media/production|box/{id}. Tự cập nhật realtime.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON, mediaImageUrl } from "../api";
import { fmtTime } from "../format";
import { onRealtime, eventMatchesBase } from "../realtime";
import { fastScrollToEl } from "../scroll";
import { Icon } from "../ui/Icon";

const epoch = (iso?: string) => Math.floor(Date.parse(iso || "") / 1000) || 0;

// Tên kho trong dòng "Chuyển kho" → link tới timeline kho đó, nháy biến động tương ứng
function placeLink(p: { id?: number | null; name?: string | null } | undefined, ts: string) {
  const name = p?.name || "Chưa xếp";
  return p?.id
    ? <a class="hist-place-lnk" href={`#/vi-tri/${p.id}/timeline?focus=biendong:${epoch(ts)}`}>{name}</a>
    : <span>{name}</span>;
}

// Cuộn tới ảnh trong khối Ảnh + nháy sáng (tái dùng cơ chế deep-link)
function focusImage(id: number) {
  const el = document.getElementById(`image-${id}`);
  if (!el) return;
  fastScrollToEl(el, "center");
  el.classList.add("flash-target");
  setTimeout(() => el.classList.remove("flash-target"), 2400);
}

export function History({ base, focusTs }: { base: string; focusTs?: number }) {
  const [items, setItems] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const listRef = useRef<HTMLUListElement>(null);
  const focusedRef = useRef(false);

  const load = () =>
    getJSON(`${base}/history`, { cache: false })
      .then((r) => { setItems(r.history || []); setLoaded(true); })
      .catch(() => {});

  useEffect(() => { load(); }, [base]);

  // Deep-link: cuộn tới + nháy thao tác có ts GẦN NHẤT focusTs (khớp theo giây)
  useEffect(() => {
    if (!focusTs || !items.length || focusedRef.current) return;
    let best = -1, bestD = Infinity;
    items.forEach((h, i) => { const dd = Math.abs(epoch(h.ts) - focusTs); if (dd < bestD) { bestD = dd; best = i; } });
    if (best < 0) return;
    focusedRef.current = true;
    const t = setTimeout(() => {
      const el = listRef.current?.children[best] as HTMLElement | undefined;
      if (!el) return;
      fastScrollToEl(el, "center");
      el.classList.add("flash-target");
      setTimeout(() => el.classList.remove("flash-target"), 2400);
    }, 140);
    return () => clearTimeout(t);
  }, [loaded, focusTs, items]);

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
      <b><Icon name="history" size={16} /> Lịch sử thao tác</b>
      {items.length ? (
        <ul class="hist" ref={listRef}>
          {items.map((h, i) => (
            <li key={`${h.ts}-${h.action}-${h.image_id ?? h.detail ?? i}`} class={h.ok === false ? "hist-fail" : ""}>
              <div class="hist-row">
                <div>
                  <div>
                    <b>{h.action}</b>
                    {h.move ? (
                      <span> · từ {placeLink(h.move.from, h.ts)} → {placeLink(h.move.to, h.ts)}</span>
                    ) : h.detail ? <span> — {h.detail}</span> : null}
                    {h.order ? (
                      <span> · <a class="hist-order-lnk"
                        href={`#/order/${h.order.thread_id}${h.order.box_id ? `?focus=box:${h.order.box_id}` : ""}`}
                        >"{h.order.text}"</a></span>
                    ) : null}
                    {h.source_slip ? (
                      <span> · <a class="hist-place-lnk" href={`#/san_xuat/${h.source_slip.thread_id}`}>Phiếu SX →</a></span>
                    ) : null}
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
