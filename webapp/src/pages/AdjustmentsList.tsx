// Dashboard PHIẾU ĐIỀU CHỈNH tồn kho (#/dieu-chinh) — mọi phiếu, nhóm theo ngày.
// Card → chi tiết THÙNG (#/thung/:id, nơi tạo/gỡ phiếu); phiếu từ kiểm kho có link
// phiếu kiểm. Data: GET /api/adjustments (listAdjustments). Realtime:
// inventory_changed/box_changed → tải lại. Phiếu đã gỡ hiện gạch (lịch sử liền mạch).
import { useEffect, useRef, useState } from "preact/hooks";
import { listAdjustments, soVN, type Adjustment } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { SearchBar } from "../ui/SearchBar";
import { EmptyState, Loading } from "../ui/states";
import { Icon } from "../ui/Icon";

let adjCache: Adjustment[] | null = null;
onRealtime((e) => {
  if (e.type === "inventory_changed" || e.type === "box_changed" || e.type === "resync") adjCache = null;
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

export function AdjustmentsList() {
  const [rows, setRows] = useState<Adjustment[]>(adjCache || []);
  const [q, setQ] = useState(memQ);
  useEffect(() => { memQ = q; }, [q]);
  const [loading, setLoading] = useState(!adjCache);

  const load = () => listAdjustments({})
    .then((r) => { setRows(r); adjCache = r; })
    .catch(() => {})
    .finally(() => setLoading(false));
  useEffect(() => { if (!adjCache) load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "inventory_changed" || e.type === "box_changed" || e.type === "resync") load();
  }), []);
  const rowsRef = useRef<Adjustment[]>([]);
  rowsRef.current = rows;
  useEffect(() => () => { if (rowsRef.current.length) adjCache = rowsRef.current; }, []);

  const fq = foldVN(q.trim());
  const visible = !fq ? rows : rows.filter((r) => foldVN(
    `${r.reason} ${r.product_code || ""} ${r.box_code || ""} ${r.created_by || ""} ${r.source === "stocktake" ? "kiem kho" : ""}`
  ).includes(fq));

  const groups: { key: string; items: Adjustment[] }[] = [];
  for (const r of visible) {
    const k = dayKey(r.created_at);
    const last = groups[groups.length - 1];
    if (last && last.key === k) last.items.push(r);
    else groups.push({ key: k, items: [r] });
  }

  return (
    <div class="ret-list">
      <div class="ret-toolbar">
        <SearchBar value={q} onInput={setQ} placeholder="Tìm lý do, SP, thùng, người tạo…" />
        <a class="btn primary" href="#/kho"><Icon name="box" size={16} /> Chọn thùng</a>
      </div>
      <div class="muted small" style={{ margin: "0 0 10px" }}>
        Sửa tồn 1 thùng cho đúng thực tế: mở thùng trong 📦 Kho → khối "Điều chỉnh tồn" (văn phòng).
        Kiểm kho áp dụng chênh lệch cũng tạo phiếu ở đây. Admin gỡ phiếu = hoàn nguyên tồn.
      </div>
      {loading && !rows.length && <Loading />}
      {!loading && !rows.length && <EmptyState>Chưa có phiếu điều chỉnh nào.</EmptyState>}
      {!loading && rows.length > 0 && !visible.length && <EmptyState>Không có phiếu khớp "{q}".</EmptyState>}
      {groups.map((g) => (
        <div class="prod-group" key={g.key}>
          <div class="prod-group-head">{dayLabel(g.key)} <span class="muted small">({g.items.length})</span></div>
          {g.items.map((r) => (
            <a class={"ret-card" + (r.deleted_at ? " adj-card-deleted" : "")} href={`#/thung/${r.box_id}`} key={r.id}>
              <div class="ret-card-top">
                <span class="ret-cust">
                  <Icon name="edit" size={14} /> {r.product_code || "?"} · thùng {(r.box_code || "").split("-").pop() || `#${r.box_id}`}
                </span>
                <span class={"disp-amt " + (r.delta > 0 ? "adj-up" : "")}>{r.delta > 0 ? "+" : "−"}{soVN(Math.abs(r.delta))}</span>
              </div>
              <div class="ret-card-sub muted small">
                {r.old_remaining != null && r.new_remaining != null ? `${soVN(r.old_remaining)} → ${soVN(r.new_remaining)} · ` : ""}
                {r.reason}
                {r.source === "stocktake" && r.stocktake_id ? ` · từ kiểm kho #${r.stocktake_id}` : ""}
                {r.created_by ? ` · ${r.created_by}` : ""}
                {r.created_at ? ` · ${r.created_at.slice(11, 16)}` : ""}
                {r.deleted_at ? ` · ĐÃ GỠ${r.deleted_by ? ` bởi ${r.deleted_by}` : ""}` : ""}
              </div>
            </a>
          ))}
        </div>
      ))}
      {visible.length > 0 && <div class="muted small" style={{ textAlign: "center", padding: "10px" }}>{visible.length} phiếu</div>}
    </div>
  );
}
