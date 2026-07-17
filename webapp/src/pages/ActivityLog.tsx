// Trang lịch sử thao tác TOÀN BỘ (#/lich-su) — gộp mọi đơn/phiếu SX/thùng.
// Data: GET /api/activity?page=N. Mỗi dòng link tới trang chi tiết tương ứng.
import { useEffect, useRef, useState } from "preact/hooks";
import { getActivity } from "../api";
import { fmtDateTimeVN, fmtRelative } from "../format";
import { EmptyState, ErrorState, Loading, LoadingInline } from "../ui/states";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";

// Cache list đã tải → quay lại giữ nguyên + hệ cuộn khôi phục vị trí (khỏi tải lại).
let actCache: { items: any[]; before: number | null; hasMore: boolean } | null = null;

// FIX realtime khi trang ĐANG UNMOUNT: bất kỳ thao tác nào (trừ lock/draft tạm) → bỏ cache
// để mount lại tải feed mới nhất. Khớp hành vi khi đang mở trang (vốn cũng reset về mới
// nhất mỗi thao tác). Không có thao tác nào lúc vắng mặt → cache còn nguyên → giữ vị trí cuộn.
onRealtime((e) => {
  if (e.type === "report_draft" || e.type === "report_lock") return;
  actCache = null;
});

export function ActivityLog() {
  const [items, setItems] = useState<any[]>([]);
  const [before, setBefore] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const snap = useRef<any>(null);
  snap.current = { items, before, hasMore };

  const load = async (cursor: number | null) => {
    setLoading(true);
    try {
      const r = await getActivity(cursor);
      setItems((prev) => (cursor == null ? r.items : [...prev, ...r.items]));
      setHasMore(!!r.has_more);
      setBefore(r.next_before ?? null);
      setErr("");
    } catch (e: any) {
      // Lỗi trang ĐẦU → hiện ErrorState (trang sau lỡ lỗi thì giữ list đã có)
      if (cursor == null) setErr(e?.message || "Không tải được lịch sử");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (actCache) {   // quay lại → dựng lại list đã tải
      setItems(actCache.items); setBefore(actCache.before); setHasMore(actCache.hasMore); setLoading(false);
      return;
    }
    load(null);
  }, []);
  useEffect(() => () => { if (snap.current?.items?.length) actCache = { ...snap.current }; }, []);

  // Realtime: bất kỳ thao tác nào (đơn/SX/thùng…) → làm mới đầu danh sách (mới nhất trước)
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "report_draft" || e.type === "report_lock") return;   // sự kiện tạm, không phải thao tác
      clearTimeout(t); t = setTimeout(() => { actCache = null; load(null); }, 800);
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  // Sentinel lazy-load: cuộn tới đáy → tự tải trang kế (nút "Tải thêm" vẫn giữ)
  const moreRef = useRef<HTMLDivElement>(null);
  const pgRef = useRef({ before, hasMore, loading });
  pgRef.current = { before, hasMore, loading };
  useEffect(() => {
    const el = moreRef.current;
    if (!el) return;
    const io = new IntersectionObserver((ents) => {
      const st = pgRef.current;
      if (ents.some((x) => x.isIntersecting) && !st.loading && st.hasMore) load(st.before);
    }, { rootMargin: "300px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [items.length]);

  return (
    <div>
      <PageHead fallback="#/home" title={<><Icon name="clock" size={18} /> Lịch sử thao tác</>} />
      {items.length ? (
        <ul class="hist act-log">
          {items.map((h, i) => (
            <li key={i} class={h.ok === false ? "hist-fail" : ""}>
              {/* div + onClick (không phải <a>) vì bên trong còn link con tới thùng/SP/khách */}
              <div class="act-item" role={h.href ? "link" : undefined}
                onClick={() => { if (h.href) location.hash = h.href.replace(/^#/, ""); }}>
                <div class="act-body">
                  <div>
                    <span class="act-scope">{h.scope_label}</span> <b>{h.action}</b>
                    {Array.isArray(h.parts) && h.parts.length > 0 ? (
                      <span> — {h.parts.map((p: any, pi: number) =>
                        p.href
                          ? <a key={pi} class="hist-place-lnk" href={p.href} onClick={(e: any) => e.stopPropagation()}>{p.t}</a>
                          : <span key={pi}>{p.t}</span>)}</span>
                    ) : h.detail ? <span> — {h.detail}</span> : null}
                    {h.peek
                      ? <span class="muted small act-peek"> · {h.peek}…</span>
                      : (h.entity_id ? <span class="muted small"> #{h.entity_id}</span> : null)}
                    {h.ok === false ? <span class="owe"> ✗ lỗi</span> : null}
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
                  <div class="muted small"><Icon name="user" size={13} /> {h.actor || "?"} · <Icon name="clock" size={13} /> {fmtDateTimeVN(h.ts)} ({fmtRelative(h.ts)})</div>
                </div>
                {h.href ? <span class="act-go muted">›</span> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : loading ? (
        <Loading />
      ) : err ? (
        <ErrorState msg={err} onRetry={() => load(null)} />
      ) : (
        <EmptyState icon="🕐">Chưa có thao tác nào được ghi.</EmptyState>
      )}
      {hasMore && <div ref={moreRef} class="io-sentinel" />}
      {!loading && hasMore && <button class="btn small wide" onClick={() => load(before)}>Tải thêm</button>}
      {loading && items.length > 0 && <p class="muted center small"><LoadingInline /></p>}
    </div>
  );
}
