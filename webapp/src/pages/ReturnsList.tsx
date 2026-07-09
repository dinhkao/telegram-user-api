// Dashboard TRẢ HÀNG (#/tra-hang) — mọi phiếu trả, nhóm theo ngày, cuộn tải thêm.
// Card → #/tra-hang/:id. Realtime: customer_changed/resync → tải lại trang 1
// (tạo/xoá phiếu trả emit customer_changed). Cache module — quay lại giữ vị trí.
import { useEffect, useRef, useState } from "preact/hooks";
import { listAllReturns, soVN, type ReturnSlip } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { ReturnModal } from "../detail/ReturnModal";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState } from "../ui/states";
import { Icon } from "../ui/Icon";

let retCache: { rows: ReturnSlip[]; page: number; totalPages: number } | null = null;
onRealtime((e) => {
  if (e.type === "customer_changed" || e.type === "return_changed" || e.type === "resync") retCache = null;
});

const dayKey = (at?: string) => (at || "").slice(0, 10);
const _WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
function dayLabel(k: string): string {
  if (!k) return "Không rõ ngày";
  const d = new Date(k);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - d.getTime()) / 86400000);
  const lbl = `${_WD[d.getDay()]} ${k.slice(8)}/${k.slice(5, 7)}`;
  if (diff === 0) return `Hôm nay · ${lbl}`;
  if (diff === 1) return `Hôm qua · ${lbl}`;
  return `${lbl}/${k.slice(0, 4)}`;
}

// Nhớ ô tìm khi rời trang
let memQ = "";

export function ReturnsList() {
  const [rows, setRows] = useState<ReturnSlip[]>(retCache?.rows || []);
  const [q, setQ] = useState(memQ);
  useEffect(() => { memQ = q; }, [q]);
  const [createOpen, setCreateOpen] = useState(false);
  const [loading, setLoading] = useState(!retCache);
  const [total, setTotal] = useState(0);
  const st = useRef({ page: retCache?.page || 1, totalPages: retCache?.totalPages || 1, loading: false });
  const sentinel = useRef<HTMLDivElement>(null);

  const load = async (page: number, append: boolean) => {
    if (st.current.loading) return;
    st.current.loading = true;
    if (!append) setLoading(true);
    try {
      const r = await listAllReturns(page);
      st.current.page = r.page;
      st.current.totalPages = r.total_pages;
      setTotal(r.total);
      setRows((prev) => (append ? [...prev, ...r.returns] : r.returns));
    } catch { /* im */ } finally {
      st.current.loading = false;
      setLoading(false);
    }
  };
  useEffect(() => { if (!retCache) load(1, false); }, []);
  // snapshot khi rời trang
  const rowsRef = useRef<ReturnSlip[]>([]);
  rowsRef.current = rows;
  useEffect(() => () => {
    if (rowsRef.current.length) retCache = { rows: rowsRef.current, page: st.current.page, totalPages: st.current.totalPages };
  }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "customer_changed" || e.type === "return_changed" || e.type === "resync") load(1, false);
  }), []);
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((es) => {
      if (!es[0].isIntersecting) return;
      const { page, totalPages, loading: ld } = st.current;
      if (ld || page >= totalPages) return;
      load(page + 1, true);
    }, { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // lọc client-side (số phiếu ít): khách / mã HĐ / SP / ghi chú / người tạo
  const fq = foldVN(q.trim());
  const visible = !fq ? rows : rows.filter((r) => foldVN(
    `${r.customer_name || ""} ${r.customer_key} ${r.kv_invoice_code || ""} ${(r.items || []).map((x) => x.sp).join(" ")} ${r.note || ""} ${r.created_by || ""}`
  ).includes(fq));

  // nhóm theo ngày
  const groups: { key: string; items: ReturnSlip[] }[] = [];
  for (const r of visible) {
    const k = dayKey(r.created_at);
    const last = groups[groups.length - 1];
    if (last && last.key === k) last.items.push(r);
    else groups.push({ key: k, items: [r] });
  }

  return (
    <div class="ret-list">
      <div class="ret-toolbar">
        <SearchBar value={q} onInput={setQ} placeholder="Tìm khách, SP, mã HĐ…" />
        <button class="btn primary" onClick={() => setCreateOpen(true)}>
          <Icon name="plus" size={16} /> Tạo phiếu
        </button>
      </div>
      {createOpen && <ReturnModal onClose={() => setCreateOpen(false)} onCreated={() => load(1, false)} />}
      {loading && !rows.length && <Loading />}
      {!loading && !rows.length && <EmptyState>Chưa có phiếu trả hàng nào.</EmptyState>}
      {!loading && rows.length > 0 && !visible.length && <EmptyState>Không có phiếu khớp "{q}".</EmptyState>}
      {groups.map((g) => (
        <div class="prod-group" key={g.key}>
          <div class="prod-group-head">{dayLabel(g.key)} <span class="muted small">({g.items.length})</span></div>
          {g.items.map((r) => (
            <a class="ret-card" href={`#/tra-hang/${r.id}`} key={r.id}>
              <div class="ret-card-top">
                <span class="ret-cust">{r.customer_name || r.customer_key}
                  {!r.kv_invoice_code && <span class="pk-badge pack"><Icon name="edit" size={11} /> Nháp</span>}
                </span>
                <span class="ret-amt">−{soVN(r.total)}</span>
              </div>
              <div class="ret-card-sub muted small">
                {(r.items || []).map((x) => `${x.sp} ×${soVN(x.sl)}`).join(", ")}
                {r.kv_invoice_code ? ` · ${r.kv_invoice_code}` : ""}
                {r.created_by ? ` · ${r.created_by}` : ""}
                {r.created_at ? ` · ${r.created_at.slice(11, 16)}` : ""}
              </div>
              {r.note && <div class="ret-card-note"><Icon name="note" size={12} /> {r.note}</div>}
            </a>
          ))}
        </div>
      ))}
      <div ref={sentinel} style={{ height: "1px" }} />
      {visible.length > 0 && <div class="muted small" style={{ textAlign: "center", padding: "10px" }}>{visible.length}/{total} phiếu</div>}
    </div>
  );
}
