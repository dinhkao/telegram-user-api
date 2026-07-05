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
import { ProductPicker } from "../detail/ProductPicker";
import { Loading, EmptyState } from "../ui/states";

// Cache list đã tải → quay lại giữ nguyên + hệ cuộn khôi phục vị trí (khỏi tải lại).
let prodCache: { slips: ProdSlip[]; page: number; totalPages: number } | null = null;

// FIX realtime khi trang ĐANG UNMOUNT (ở trang khác): handler trong component chết nên
// bỏ lỡ event → quay lại thấy cache cũ. Subscriber cấp-module này LUÔN sống, VÁ prodCache
// tại chỗ (giữ vị trí cuộn, KHÔNG co về trang 1). Chỉ bỏ cache khi thêm/xoá phiếu (cấu
// trúc list đổi) hoặc reconnect.
onRealtime((e) => {
  if (e.type === "productions_changed" || e.type === "resync") { prodCache = null; return; }
  if (e.type !== "production_changed" || !prodCache) return;
  const idx = prodCache.slips.findIndex((s) => String(s.thread_id) === e.thread_id);
  if (e.row === null) {
    if (idx >= 0) prodCache = { ...prodCache, slips: prodCache.slips.filter((_, i) => i !== idx) };
  } else if (idx >= 0) {
    const next = prodCache.slips.slice();
    next[idx] = { ...next[idx], ...(e.row as ProdSlip) };
    prodCache = { ...prodCache, slips: next };
  }
});

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
    if (prodCache) {   // quay lại → dựng lại list đã tải (đủ cao cho hệ cuộn khôi phục)
      setSlips(prodCache.slips);
      st.current.page = prodCache.page;
      st.current.totalPages = prodCache.totalPages;
    } else {
      load(1, false);
    }
    productionCatalog().then(setCatalog).catch(() => {});
  }, []);
  // Lưu snapshot khi rời trang
  const slipsRef = useRef<ProdSlip[]>([]);
  slipsRef.current = slips;
  useEffect(() => () => {
    if (slipsRef.current.length) prodCache = { slips: slipsRef.current, page: st.current.page, totalPages: st.current.totalPages };
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
        <ProductPicker catalog={catalog} value={newCode} onPick={setNewCode} placeholder="🔍 Tìm mã SP (tuỳ chọn)" />
        <button class="btn primary" disabled={creating} onClick={doCreate}>
          {creating ? "Đang tạo…" : "➕ Tạo phiếu"}
        </button>
      </div>

      {err && <div class="error-banner">{err}</div>}
      {loading && !slips.length && <Loading />}
      {!loading && !slips.length && <EmptyState>Chưa có phiếu sản xuất nào.</EmptyState>}

      <div class="prod-cards">
        {groupByDay(slips).map((g) => (
          <div class="prod-group" key={g.key}>
            <div class="prod-group-head">{g.label} <span class="muted small">({g.slips.length})</span></div>
            {g.slips.map((s) => <ProdCard key={s.thread_id} slip={s} />)}
          </div>
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

const _WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

/** Nhóm phiếu theo NGÀY tạo (slip đã sắp mới→cũ). Trả [{key, label, slips}]. */
function groupByDay(slips: ProdSlip[]): { key: string; label: string; slips: ProdSlip[] }[] {
  const out: { key: string; label: string; slips: ProdSlip[] }[] = [];
  for (const s of slips) {
    const key = (prodCreated(s).split(" ")[0]) || "?";   // "DD/MM/YYYY"
    const last = out[out.length - 1];
    if (last && last.key === key) last.slips.push(s);
    else out.push({ key, label: dayLabel(key), slips: [s] });
  }
  return out;
}

function dayLabel(key: string): string {
  const [d, m, y] = key.split("/").map(Number);
  if (!d || !m || !y) return "Không rõ ngày";
  const date = new Date(y, m - 1, d);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - date.getTime()) / 86400000);
  const wd = _WD[date.getDay()];
  const dm = `${key.slice(0, 5)}`; // DD/MM
  if (diff === 0) return `Hôm nay · ${wd} ${dm}`;
  if (diff === 1) return `Hôm qua · ${wd} ${dm}`;
  return `${wd} · ${key}`;
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
        <span class="prod-date">🕒 {(() => { const c = prodCreated(slip); return c.includes(" ") ? c.split(" ")[1] : c; })()}</span>
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
      {slip.ghi_chu && <div class="prod-card-note">📝 {slip.ghi_chu}</div>}
    </a>
  );
}
