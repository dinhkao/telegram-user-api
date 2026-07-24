// Dashboard KHU VỰC XƯỞNG (#/khu-vuc) — mỗi khu 1 card: ảnh + trạng thái vệ sinh
// HÔM NAY (✓ đã vệ sinh / chưa báo cáo) + dải 7 ngày. Tạo khu vực (mọi user) →
// vào chi tiết chụp ảnh. Data: listAreas. Realtime area_changed → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { listAreas, createArea, mediaImageUrl, type AreaRow } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SearchBar } from "../ui/SearchBar";
import { toast, promptDialog } from "../ui/feedback";
import { Loading, EmptyState, ErrorState } from "../ui/states";

let areasCache: AreaRow[] | null = null;
onRealtime((e) => { if (e.type === "area_changed" || e.type === "resync") areasCache = null; });

function dow(ymd: string): string {
  const d = new Date(ymd + "T00:00:00");
  return ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][d.getDay()] || "";
}

export function AreasBoard() {
  const [rows, setRows] = useState<AreaRow[] | null>(areasCache);
  const [today, setToday] = useState("");
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);

  const load = async () => {
    try {
      const b = await listAreas();
      setRows(b.areas); areasCache = b.areas;
      setToday(b.today_ymd); setDone(b.done_count); setTotal(b.total); setErr("");
    } catch (e: any) { setErr(e?.message || "Lỗi tải khu vực"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "area_changed" || e.type === "resync") load();
  }), []);
  const rowsRef = useRef<AreaRow[]>([]);
  rowsRef.current = rows || [];
  useEffect(() => () => { if (rowsRef.current.length) areasCache = rowsRef.current; }, []);

  const doAdd = async () => {
    const name = (await promptDialog("Tên khu vực mới (vd: Khu đóng gói)", { okLabel: "Tạo" }))?.trim();
    if (!name) return;
    setAdding(true);
    try {
      const a = await createArea(name);
      toast(`✅ Đã tạo "${a.name}"`, "ok");
      await load();
      window.location.hash = `#/khu-vuc/${a.id}`;
    } catch (e: any) { toast(e?.message || "Lỗi tạo khu vực", "err"); }
    finally { setAdding(false); }
  };

  if (err && !rows) return <ErrorState msg={err} onRetry={load} />;
  if (!rows) return <Loading />;

  const nq = foldVN(q.trim());
  const shown = nq ? rows.filter((r) => foldVN(r.name + " " + r.note).includes(nq)) : rows;

  return (
    <div class="inv-dash">
      <PageHead title={<span><Icon name="leaf" size={18} /> Khu vực xưởng</span>}
        sub="Báo cáo vệ sinh hàng ngày" fallback="#/orders"
        right={<button class="btn small primary" disabled={adding} onClick={doAdd}><Icon name="plus" size={15} /> Thêm khu vực</button>} />

      <div class={"area-summary " + (total > 0 && done >= total ? "all-done" : "")}>
        <Icon name="check" size={16} />
        <span>Hôm nay: <b>{done}/{total}</b> khu vực đã báo cáo</span>
      </div>

      <SearchBar value={q} onInput={setQ} placeholder="Tìm tên khu vực…" />

      {rows.length === 0 ? (
        <EmptyState>Chưa có khu vực nào. Bấm "Thêm khu vực" ở trên.</EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState>Không có khu vực khớp "{q.trim()}".</EmptyState>
      ) : (
        <div class="area-grid">
          {shown.map((a) => (
            <a class="area-card" href={`#/khu-vuc/${a.id}`} key={a.id}>
              <div class="area-thumb">
                {a.thumb_image_id != null && a.thumb_report_id != null ? (
                  <img loading="lazy" alt=""
                    src={mediaImageUrl(`/api/media/area_report/${a.thumb_report_id}`, a.thumb_image_id, "thumb")} />
                ) : (
                  <span class="area-thumb-ph"><Icon name="camera" size={22} /></span>
                )}
              </div>
              <div class="area-card-body">
                <div class="area-card-name">{a.name}</div>
                <div class={"area-badge " + (a.today.reported ? "t-ok" : "t-danger")}>
                  {a.today.reported ? "✓ Đã vệ sinh" : "Chưa báo cáo"}
                </div>
                {a.last_report && (
                  <div class="muted small">
                    BC gần nhất: {a.last_report.ymd}{a.last_report.created_by ? ` · ${a.last_report.created_by}` : ""}
                  </div>
                )}
                <div class="area-week">
                  {a.week.map((d) => (
                    <span class={"area-dot " + (d.reported ? "on" : "") + (d.ymd === today ? " today" : "")}
                      key={d.ymd} title={`${dow(d.ymd)} ${d.ymd} — ${d.reported ? "đã báo cáo" : "chưa"}`} />
                  ))}
                </div>
              </div>
              <Icon name="chevronRight" size={18} class="kg-arrow" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
