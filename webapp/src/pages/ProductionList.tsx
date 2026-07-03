// Danh sách phiếu sản xuất — GET /api/production (phân trang 20/trang, cuộn tải
// thêm như dashboard đơn). Card → #/san_xuat/:thread_id. Tạo phiếu mới ở đầu.
// Realtime: productions_changed/resync → tải lại trang 1; production_changed → vá.
import { useEffect, useRef, useState } from "preact/hooks";
import {
  listProduction,
  createProduction,
  productionCatalog,
  soVN,
  prodCreated,
  type ProdSlip,
  type ProdCatalogItem,
} from "../api";
import { onRealtime } from "../realtime";

export function ProductionList() {
  const [slips, setSlips] = useState<ProdSlip[]>([]);
  const [catalog, setCatalog] = useState<ProdCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [err, setErr] = useState("");
  const [total, setTotal] = useState(0);
  const st = useRef({ page: 1, totalPages: 1, loading: false });
  const sentinel = useRef<HTMLDivElement>(null);

  const load = async (page: number, append: boolean) => {
    if (st.current.loading) return;
    st.current.loading = true;
    if (!append) setLoading(true);
    try {
      const r = await listProduction(page);
      st.current.page = r.page;
      st.current.totalPages = r.total_pages;
      setTotal(r.total);
      setSlips((prev) => (append ? [...prev, ...r.slips] : r.slips));
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải danh sách");
    } finally {
      st.current.loading = false;
      setLoading(false);
    }
  };

  useEffect(() => {
    load(1, false);
    productionCatalog().then(setCatalog).catch(() => {});
  }, []);

  // Realtime
  useEffect(() => {
    return onRealtime((e) => {
      if (e.type === "productions_changed" || e.type === "resync") {
        load(1, false);
        return;
      }
      if (e.type !== "production_changed") return;
      const tid = e.thread_id;
      setSlips((prev) => {
        const idx = prev.findIndex((s) => String(s.thread_id) === tid);
        if (e.row === null) return idx >= 0 ? prev.filter((_, i) => i !== idx) : prev;
        if (idx >= 0) {
          const next = prev.slice();
          next[idx] = { ...next[idx], ...(e.row as ProdSlip) };
          return next;
        }
        return [e.row as ProdSlip, ...prev];
      });
    });
  }, []);

  // Cuộn tải thêm (như OrdersList)
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) return;
        const { page, totalPages, loading: ld } = st.current;
        if (ld || page >= totalPages) return;
        load(page + 1, true);
      },
      { rootMargin: "300px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const doCreate = async () => {
    setCreating(true);
    setErr("");
    try {
      const tid = await createProduction(newCode || undefined);
      window.location.hash = `#/san_xuat/${tid}`;
    } catch (e: any) {
      setErr(e?.message || "Tạo phiếu thất bại");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div class="prod-list">
      <div class="prod-create">
        <select value={newCode} onChange={(e) => setNewCode((e.target as HTMLSelectElement).value)}>
          <option value="">— Chọn SP (tuỳ chọn) —</option>
          {catalog.map((c) => (
            <option value={c.code}>{c.code}</option>
          ))}
        </select>
        <button class="btn primary" disabled={creating} onClick={doCreate}>
          {creating ? "Đang tạo…" : "➕ Tạo phiếu"}
        </button>
      </div>

      {err && <div class="error-banner">{err}</div>}
      {loading && !slips.length && <div class="muted">Đang tải…</div>}
      {!loading && !slips.length && <div class="muted">Chưa có phiếu sản xuất nào.</div>}

      <div class="prod-cards">
        {slips.map((s) => (
          <ProdCard key={s.thread_id} slip={s} />
        ))}
      </div>

      <div ref={sentinel} style={{ height: "1px" }} />
      {slips.length > 0 && (
        <div class="muted small" style={{ textAlign: "center", padding: "10px" }}>
          {slips.length}/{total} phiếu
        </div>
      )}
    </div>
  );
}

function ProdCard({ slip }: { slip: ProdSlip }) {
  const total = slip.total || 0;
  const target = slip.sx_target ?? slip.target ?? null;
  const pct = target ? Math.min(Math.round((total / target) * 100), 100) : null;
  const done = target != null && total >= target;
  return (
    <a class="prod-card" href={`#/san_xuat/${slip.thread_id}`}>
      <div class="prod-card-top">
        <span class="prod-sp">{slip.sp_name || "Chưa có SP"}</span>
        <span class="prod-date">📅 {prodCreated(slip)}</span>
      </div>
      <div class="prod-card-stat">
        <span class={done ? "prod-total done" : "prod-total"}>✅ {soVN(total)}</span>
        <span class="prod-target">🎯 {target != null ? soVN(target) : "—"}</span>
      </div>
      {pct != null && (
        <div class="prod-bar">
          <div class={done ? "prod-bar-fill done" : "prod-bar-fill"} style={{ width: `${pct}%` }} />
        </div>
      )}
    </a>
  );
}
