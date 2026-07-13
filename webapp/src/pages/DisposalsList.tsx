// Dashboard XUẤT HỦY (#/xuat-huy) — mọi phiếu hủy hàng, nhóm theo ngày. Card →
// #/xuat-huy/:id. Tạo phiếu = nút "Xuất hủy" ở trang chi tiết THÙNG (#/thung/:id)
// — hủy tại chỗ khi thấy hàng hư. Realtime: disposal_changed → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { listDisposals, soVN, type DisposalSlip } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { SearchBar } from "../ui/SearchBar";
import { EmptyState, Loading } from "../ui/states";
import { Icon } from "../ui/Icon";

let dispCache: DisposalSlip[] | null = null;
onRealtime((e) => {
  if (e.type === "disposal_changed" || e.type === "resync") dispCache = null;
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

let memQ = "";

export function DisposalsList() {
  const [rows, setRows] = useState<DisposalSlip[]>(dispCache || []);
  const [q, setQ] = useState(memQ);
  useEffect(() => { memQ = q; }, [q]);
  const [loading, setLoading] = useState(!dispCache);

  const load = () => listDisposals()
    .then((r) => { setRows(r); dispCache = r; })
    .catch(() => {})
    .finally(() => setLoading(false));
  useEffect(() => { if (!dispCache) load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "disposal_changed" || e.type === "resync") load();
  }), []);
  const rowsRef = useRef<DisposalSlip[]>([]);
  rowsRef.current = rows;
  useEffect(() => () => { if (rowsRef.current.length) dispCache = rowsRef.current; }, []);

  const fq = foldVN(q.trim());
  const visible = !fq ? rows : rows.filter((r) => foldVN(
    `${r.reason} ${(r.items || []).map((x) => `${x.product_code} ${x.box_code}`).join(" ")} ${r.created_by || ""}`
  ).includes(fq));

  const groups: { key: string; items: DisposalSlip[] }[] = [];
  for (const r of visible) {
    const k = dayKey(r.created_at);
    const last = groups[groups.length - 1];
    if (last && last.key === k) last.items.push(r);
    else groups.push({ key: k, items: [r] });
  }

  return (
    <div class="ret-list">
      <div class="ret-toolbar">
        <SearchBar value={q} onInput={setQ} placeholder="Tìm lý do, SP, thùng…" />
        <a class="btn primary" href="#/kho"><Icon name="box" size={16} /> Chọn thùng</a>
      </div>
      <div class="muted small" style={{ margin: "0 0 10px" }}>
        Hủy hàng hư/hết hạn: mở thùng trong 📦 Kho → bấm "Xuất hủy". Tồn thùng trừ ngay, xoá phiếu (admin) sẽ hoàn lại.
      </div>
      {loading && !rows.length && <Loading />}
      {!loading && !rows.length && <EmptyState>Chưa có phiếu xuất hủy nào.</EmptyState>}
      {!loading && rows.length > 0 && !visible.length && <EmptyState>Không có phiếu khớp "{q}".</EmptyState>}
      {groups.map((g) => (
        <div class="prod-group" key={g.key}>
          <div class="prod-group-head">{dayLabel(g.key)} <span class="muted small">({g.items.length})</span></div>
          {g.items.map((r) => (
            <a class="ret-card" href={`#/xuat-huy/${r.id}`} key={r.id}>
              <div class="ret-card-top">
                <span class="ret-cust"><Icon name="trash" size={14} /> {r.reason}</span>
                <span class="disp-amt">−{soVN(r.total_quantity)}</span>
              </div>
              <div class="ret-card-sub muted small">
                {(r.items || []).map((x) => `${x.product_code} ×${soVN(x.quantity)} (thùng ${(x.box_code || "").split("-").pop()})`).join(", ")}
                {r.created_by ? ` · ${r.created_by}` : ""}
                {r.created_at ? ` · ${r.created_at.slice(11, 16)}` : ""}
              </div>
            </a>
          ))}
        </div>
      ))}
      {visible.length > 0 && <div class="muted small" style={{ textAlign: "center", padding: "10px" }}>{visible.length} phiếu</div>}
    </div>
  );
}
