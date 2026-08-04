// LƯƠNG SP THEO NGÀY (#/luong-ngay) — CHỈ văn phòng. Bảng PIVOT: mỗi THỢ một CỘT,
// mỗi NGÀY một HÀNG (ngược với sheet cũ của văn phòng — để thêm ngày là kéo dài
// xuống, khỏi phải kéo ngang). 2 kiểu xem:
//   · Theo ngày  — 1 hàng = 1 ngày (tổng tiền công ngày đó của từng thợ),
//   · Chi tiết   — dưới mỗi ngày là TỪNG PHIẾU SX (mã SP + giờ), mỗi phiếu 1 hàng.
// Ô tô ĐẬM NHẠT theo số tiền (heatmap) để nhìn phát thấy ai/ngày nào làm nhiều.
// Số hiện theo NGHÌN đồng cho gọn (rê chuột thấy số đầy đủ).
// Data: GET /api/production/wage-pivot (production_store/wage_pivot.py) — tiền lấy
// nguyên từ compute_range_report nên khớp phiếu báo cáo SX và bảng lương tháng.
import { useEffect, useMemo, useState } from "preact/hooks";
import { getWagePivot, isOffice, type WagePivot as Pivot } from "../api";
import { moneyR as money, curYM, shiftYM, ymLabel } from "../format";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";

/** Tiền → NGHÌN đồng, gọn nhất có thể ("487.540" → "488"). 0/rỗng → "" (ô trống
 *  đọc nhanh hơn ô đầy số 0 — sheet cũ đầy số 0 nhìn rất rối). */
const k = (v?: number) => (v ? String(Math.round(v / 1000)) : "");
const dayNum = (ymd: string) => Number(ymd.slice(8, 10));
const DOW = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const dowOf = (ymd: string) => DOW[new Date(`${ymd}T00:00:00`).getDay()];
/** Tên cột: bỏ họ, giữ tối đa 2 chữ cuối ("Nguyễn Bảo Xuyên" → "Bảo Xuyên"). */
const shortName = (n: string) => n.trim().split(/\s+/).slice(-2).join(" ");

/** Nền heatmap: càng nhiều tiền càng đậm. Mũ 0,7 để nhóm số nhỏ vẫn phân biệt được
 *  (tuyến tính thì mọi ô nhỏ đều gần như trắng như nhau). */
function heat(v: number, max: number): string {
  if (!v || max <= 0) return "";
  const t = Math.min(1, v / max);
  return `background:rgba(214,69,69,${(0.06 + 0.62 * Math.pow(t, 0.7)).toFixed(3)})`;
}

const monthRange = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return { from: `${ym}-01`, to: `${ym}-${String(last).padStart(2, "0")}` };
};

export function WagePivot() {
  const [ym, setYm] = useState(curYM);
  const [view, setView] = useState<"day" | "slip">("day");
  const [data, setData] = useState<Pivot | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = () => {
    setLoading(true);
    const { from, to } = monthRange(ym);
    getWagePivot(from, to)
      .then((d) => { setData(d); setErr(""); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải bảng lương theo ngày"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [ym]);

  // View chi tiết có thang màu RIÊNG (ô phiếu luôn nhỏ hơn ô ngày — dùng chung
  // thang thì cả bảng chi tiết nhạt thếch, không phân biệt được gì)
  const maxSlip = useMemo(() => {
    let m = 0;
    for (const d of data?.days || []) for (const s of d.slips) for (const v of Object.values(s.cells)) m = Math.max(m, v);
    return m;
  }, [data]);

  const head = (
    <PageHead fallback="#/home"
      title={<><Icon name="wallet" size={18} /> Lương SP theo ngày</>}
      sub="thợ theo cột · ngày theo hàng · đơn vị NGHÌN đồng" />
  );
  if (!isOffice()) return <div class="pr-page">{head}<EmptyState icon="🔒">Chỉ văn phòng.</EmptyState></div>;

  const ws = data?.workers || [];
  return (
    <div class="pr-page wp-page">
      {head}
      <div class="pr-controlbar">
        <div class="pr-monthbar">
          <button class="pr-mnav previous" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước"><Icon name="chevronRight" size={18} /></button>
          <div class="pr-period"><span>Kỳ</span><b>{ymLabel(ym)}</b></div>
          <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau"><Icon name="chevronRight" size={18} /></button>
        </div>
        <div class="seg" role="group" aria-label="Kiểu xem">
          <button class={view === "day" ? "seg-btn active" : "seg-btn"} onClick={() => setView("day")}>Theo ngày</button>
          <button class={view === "slip" ? "seg-btn active" : "seg-btn"} onClick={() => setView("slip")}>Chi tiết phiếu</button>
        </div>
      </div>

      {loading && !data ? <Loading />
        : err && !data ? <ErrorState msg={err} onRetry={load} />
        : !data || !ws.length ? <EmptyState icon="🏭">Tháng này chưa có báo cáo sản xuất nào.</EmptyState>
        : (
          <>
            <div class="wp-sum">
              <span>Tổng tiền công <b>{money(data.grand)}đ</b></span>
              <span class="muted small">{ws.length} thợ · {data.days.length} ngày có làm</span>
            </div>
            <div class="wp-wrap">
              <table class="wp-table">
                <thead>
                  <tr>
                    <th class="wp-cnr">Ngày</th>
                    {ws.map((w) => <th key={w.id} title={`${w.name} — ${money(w.total)}đ cả kỳ`}>{shortName(w.name)}</th>)}
                    <th class="wp-tot">Tổng</th>
                  </tr>
                </thead>
                <tbody>
                  {data.days.map((d) => (
                    <>
                      <tr key={d.ymd} class={view === "slip" ? "wp-dayrow grouped" : "wp-dayrow"}>
                        <th class="wp-day" title={d.ymd}>
                          <b>{dayNum(d.ymd)}</b> <span class="muted">{dowOf(d.ymd)}</span>
                        </th>
                        {ws.map((w) => {
                          const v = d.cells[String(w.id)] || 0;
                          return (
                            <td key={w.id} style={heat(v, data.max_cell)}
                              title={v ? `${w.name} · ${d.ymd} — ${money(v)}đ` : ""}>{k(v)}</td>
                          );
                        })}
                        <td class="wp-tot">{k(d.total)}</td>
                      </tr>
                      {/* view CHI TIẾT: mỗi phiếu SX trong ngày là 1 hàng con */}
                      {view === "slip" && d.slips.map((s) => (
                        <tr key={`${d.ymd}-${s.thread_id}`} class="wp-sliprow">
                          <th class="wp-slip" title={`Phiếu #${s.thread_id}`}>
                            <a href={`#/san_xuat/${s.thread_id}`}>{s.code || "—"}</a>
                            {s.start ? <span class="muted"> {s.start}</span> : null}
                          </th>
                          {ws.map((w) => {
                            const v = s.cells[String(w.id)] || 0;
                            return (
                              <td key={w.id} style={heat(v, maxSlip)}
                                title={v ? `${w.name} · ${s.code} ${s.start}–${s.end} — ${money(v)}đ` : ""}>{k(v)}</td>
                            );
                          })}
                          <td class="wp-tot">{k(s.total)}</td>
                        </tr>
                      ))}
                    </>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th class="wp-cnr">Tổng</th>
                    {ws.map((w) => <td key={w.id} title={`${w.name} — ${money(w.total)}đ`}>{k(w.total)}</td>)}
                    <td class="wp-tot">{k(data.grand)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <p class="muted small wp-note">Số hiện theo <b>nghìn đồng</b> (rê chuột / chạm giữ để xem số đầy đủ).
              Ô càng đậm là tiền công càng nhiều. Cột <b>Chi tiết phiếu</b> bấm được để mở phiếu SX.</p>
          </>
        )}
    </div>
  );
}
