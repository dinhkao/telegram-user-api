// Danh sách phiếu sản xuất — GET /api/production. Card → #/san_xuat/:thread_id.
// Tạo phiếu mới (mở forum topic group SX) ngay trên đầu trang. Realtime:
// productions_changed/resync → tải lại; production_changed → vá dòng tại chỗ.
import { useEffect, useRef, useState } from "preact/hooks";
import {
  listProduction,
  createProduction,
  productionCatalog,
  soVN,
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
  const st = useRef<ProdSlip[]>([]);
  st.current = slips;

  const load = async () => {
    try {
      const rows = await listProduction();
      setSlips(rows);
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải danh sách");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    productionCatalog().then(setCatalog).catch(() => {});
  }, []);

  // Realtime
  useEffect(() => {
    return onRealtime((e) => {
      if (e.type === "productions_changed" || e.type === "resync") {
        load();
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
      {loading && <div class="muted">Đang tải…</div>}
      {!loading && !slips.length && <div class="muted">Chưa có phiếu sản xuất nào.</div>}

      <div class="prod-cards">
        {slips.map((s) => (
          <ProdCard key={s.thread_id} slip={s} />
        ))}
      </div>
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
        <span class="prod-date">{slip.date || ""}</span>
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
