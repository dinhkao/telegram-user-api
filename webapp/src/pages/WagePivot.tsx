// LƯƠNG SP THEO NGÀY (#/luong-ngay) — CHỈ văn phòng. Bảng PIVOT: mỗi THỢ một CỘT,
// mỗi NGÀY một HÀNG (ngược với sheet cũ của văn phòng — để thêm ngày là kéo dài
// xuống, khỏi phải kéo ngang). 2 kiểu xem:
//   · Theo ngày  — 1 hàng = 1 ngày (tổng tiền công ngày đó của từng thợ),
//   · Chi tiết   — dưới mỗi ngày là TỪNG PHIẾU SX (mã SP + giờ), mỗi phiếu 1 hàng.
// Ô tô ĐẬM NHẠT theo số tiền (heatmap) để nhìn phát thấy ai/ngày nào làm nhiều.
// Số hiện theo NGHÌN đồng cho gọn (rê chuột thấy số đầy đủ). BẤM 1 Ô = popup chi
// tiết cấu thành số tiền ô đó (detail/WagePivotCell). View chi tiết: cột đầu 2 dòng
// = mã SP (link phiếu) / giờ bắt đầu–kết thúc (giờ tô cam = phiếu có tăng ca). Nhớ tháng/kiểu xem/vị trí cuộn.
// Data: GET /api/production/wage-pivot (production_store/wage_pivot.py) — tiền lấy
// nguyên từ compute_range_report nên khớp phiếu báo cáo SX và bảng lương tháng.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { getWagePivot, isOffice, type WagePivot as Pivot, type WagePivotSlip } from "../api";
import { moneyR as money, curYM, shiftYM, ymLabel } from "../format";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { WagePivotCell, type PivotCell } from "../detail/WagePivotCell";
import { dayFlag, slipFlag, type FlagState } from "../detail/wagePivotData";

/** class cho ô có ghi chú lệch chuẩn (dấu góc ⚠ — xem .wp-flag trong styles.css). */
const flagCls = (f: FlagState) => (f === "open" ? " wp-flag" : f === "done" ? " wp-flag done" : "");
const FLAG_TIP = " · ⚠ ghi chú lệch câu chuẩn → phụ cấp KHÔNG tự tính";

/** Tiền → NGHÌN đồng, gọn nhất có thể ("487.540" → "488"). Không có tiền thì in
 *  đúng số "0" (không bỏ trống): ô trống dễ bị đọc nhầm là thiếu dữ liệu, còn 0 là
 *  khẳng định "ngày đó thợ này không có tiền công". */
const k = (v?: number) => String(Math.round((v || 0) / 1000));
const dayNum = (ymd: string) => Number(ymd.slice(8, 10));
const DOW = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const dowOf = (ymd: string) => DOW[new Date(`${ymd}T00:00:00`).getDay()];
/** "07:45" → "7:45": bỏ số 0 đầu giờ cho cột phiếu gọn hơn (không mất thông tin). */
const hm = (t?: string) => (t || "").replace(/^0(\d)/, "$1");
/** Giờ của 1 phiếu cho cột đầu: "7:45–11:30"; thiếu giờ xong → "7:45–?"; không giờ → "—". */
const slipSpan = (s: { start: string; end: string }) =>
  s.start || s.end ? `${hm(s.start) || "?"}–${hm(s.end) || "?"}` : "—";
/** Phiếu có ai được tính TĂNG CA không → tô giờ màu cảnh báo cho dễ thấy. */
const slipHasOt = (s: WagePivotSlip) =>
  Object.values(s.parts || {}).some((ps) => ps.some((p) => (p.ot || 0) > 0));
/** Tên cột: bỏ họ, giữ tối đa 2 chữ cuối ("Nguyễn Bảo Xuyên" → "Bảo Xuyên"). */
const shortName = (n: string) => n.trim().split(/\s+/).slice(-2).join(" ");

/** Nền heatmap: càng nhiều tiền càng đậm. Mũ 0,7 để nhóm số nhỏ vẫn phân biệt được
 *  (tuyến tính thì mọi ô nhỏ đều gần như trắng như nhau). */
function heat(v: number, max: number): string {
  if (!v || max <= 0) return "";
  const t = Math.min(1, v / max);
  return `background:rgba(214,69,69,${(0.06 + 0.62 * Math.pow(t, 0.7)).toFixed(3)})`;
}

// NHỚ theo PHIÊN: tháng + kiểu xem + vị trí cuộn (cả 2 chiều) của khung bảng. Bảng
// rất rộng và dài — mở 1 ô rồi quay lại mà bảng nhảy về góc trên trái thì phải dò
// lại từ đầu. Module scope: reset khi tải lại app, giống các trang lazy-load khác.
let _saved: { ym: string; view: "day" | "slip"; left: number } | null = null;

const monthRange = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return { from: `${ym}-01`, to: `${ym}-${String(last).padStart(2, "0")}` };
};

export function WagePivot() {
  const [ym, setYm] = useState(() => _saved?.ym || curYM());
  const [view, setView] = useState<"day" | "slip">(() => _saved?.view || "day");
  const [cell, setCell] = useState<PivotCell | null>(null);
  // hàng vừa bấm (ngày, hoặc phiếu trong ngày) — giữ sáng sau khi đóng popup
  const [activeRow, setActiveRow] = useState<string>("");
  const [data, setData] = useState<Pivot | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);

  // Cuộn GIỐNG BẢNG LƯƠNG THÁNG: trang cuộn DỌC bình thường (không ép chiều cao
  // khung), bảng chỉ cuộn NGANG trong .wp-tbody-scroll; hàng tiêu đề tách ra thanh
  // sticky top và đồng bộ scrollLeft từ thân. Trước đây ép max-height theo màn hình
  // → khung cứng đơ, cuộn lồng nhau, không hợp với các trang khác.
  const headRef = useRef<HTMLDivElement>(null);
  const footRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const head = headRef.current, body = wrapRef.current, foot = footRef.current;
    if (!head || !body) return;
    const sync = () => { head.scrollLeft = body.scrollLeft; if (foot) foot.scrollLeft = body.scrollLeft; };
    const ro = new ResizeObserver(sync);
    ro.observe(body);
    window.addEventListener("resize", sync);
    return () => { ro.disconnect(); window.removeEventListener("resize", sync); };
  }, [data, view]);

  // KHÔI PHỤC vị trí cuộn sau khi bảng đã dựng xong (chỉ khi đúng tháng + kiểu xem
  // đã lưu — đổi tháng thì về đầu bảng cho khỏi lạc).
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || !data || !_saved || _saved.ym !== ym || _saved.view !== view) return;
    el.scrollLeft = _saved.left;
  }, [data, view, ym]);

  const load = () => {
    setLoading(true);
    const { from, to } = monthRange(ym);
    getWagePivot(from, to)
      .then((d) => { setData(d); setErr(""); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải bảng lương theo ngày"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [ym]);
  // ghi nhớ tháng/kiểu xem ngay khi đổi (vị trí cuộn ghi trong onScroll)
  useEffect(() => { _saved = { ...(_saved || { left: 0 }), ym, view }; }, [ym, view]);

  // View chi tiết có thang màu RIÊNG (ô phiếu luôn nhỏ hơn ô ngày — dùng chung
  // thang thì cả bảng chi tiết nhạt thếch, không phân biệt được gì)
  const maxSlip = useMemo(() => {
    let m = 0;
    for (const d of data?.days || []) for (const s of d.slips) for (const v of Object.values(s.cells)) m = Math.max(m, v);
    return m;
  }, [data]);

  // Số ô ⚠ CHƯA xử lý ĐANG HIỆN (view ngày đếm ô thợ×ngày, view chi tiết đếm ô thợ×phiếu)
  const openFlags = useMemo(() => {
    let n = 0;
    for (const d of data?.days || []) {
      if (view === "day") { for (const w of data?.workers || []) if (dayFlag(d, w.id) === "open") n++; }
      else for (const s of d.slips) for (const f of Object.values(s.flag || {})) if (!f.done) n++;
    }
    return n;
  }, [data, view]);
  // Bấm dòng cảnh báo → cuộn tới ô ⚠ KẾ TIẾP (vòng lại từ đầu) + nháy sáng ô đó
  const flagIdx = useRef(-1);
  useEffect(() => { flagIdx.current = -1; }, [data, view]);
  const [flagPos, setFlagPos] = useState(0);
  const gotoNextFlag = () => {
    const cells = Array.from(wrapRef.current?.querySelectorAll<HTMLElement>("td.wp-flag:not(.done)") || []);
    if (!cells.length) return;
    flagIdx.current = (flagIdx.current + 1) % cells.length;
    const el = cells[flagIdx.current];
    setFlagPos(flagIdx.current + 1);
    el.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
    el.classList.remove("wp-flash");
    void el.offsetWidth;            // khởi động lại animation khi bấm trúng lại ô cũ
    el.classList.add("wp-flash");
    const row = el.parentElement?.getAttribute("data-row");
    if (row) setActiveRow(row);
    window.setTimeout(() => el.classList.remove("wp-flash"), 2600);
  };

  // Bề rộng cột theo EM (font bảng .62rem) — số hiện theo nghìn nên 4 chữ số là đủ;
  // tên thợ ở tiêu đề tự xuống 2 dòng trong bề rộng này.
  const ws0 = data?.workers || [];
  // view chi tiết: ô đầu xếp 2 DÒNG (mã SP / giờ bắt đầu–kết thúc chữ nhỏ) nên chỉ
  // nhỉnh hơn view ngày một chút — trước để 1 dòng "MÃ 07:45" tốn 9,6em mà chưa đủ giờ.
  // 6,6em đo cho mã 8 ký tự ("KDXDB-MY") và giờ dài nhất "10:45–11:30".
  const COL_EM = [view === "slip" ? 6.6 : 5.8, ...ws0.map(() => 4.3), 5.0];
  const tableStyle = `min-width:${COL_EM.reduce((a, b) => a + b, 0)}em`;
  const cols = <colgroup>{COL_EM.map((w, i) => <col key={i} style={`width:${w}em`} />)}</colgroup>;

  const head = (
    <PageHead fallback="#/home"
      title={<><Icon name="wallet" size={18} /> Lương SP theo ngày</>}
      sub="thợ theo cột · đủ mọi ngày trong tháng · đơn vị NGHÌN đồng" />
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
              <span class="muted small">{ws.length} thợ · {data.days.length} ngày</span>
            </div>
            <p class="muted small wp-note">Số theo <b>nghìn đồng</b> · ô càng đậm tiền càng nhiều ·
              bấm 1 ô để xem cách tính.</p>
            {openFlags ? (
              <button type="button" class="wp-flag-note" onClick={gotoNextFlag}>
                <span class="wp-flag-key" aria-hidden="true">!</span>
                <span><b>{openFlags} ô</b> có ghi chú lệch câu chuẩn — phụ cấp <b>không tự tính</b>, văn phòng cần
                  xem và nhập tay. <u>Bấm để tới ô cần xem{flagPos ? ` (${Math.min(flagPos, openFlags)}/${openFlags})` : ""}</u>.</span>
              </button>
            ) : null}
            <div class="wp-wrap">
              <div class="wp-thead-bar" ref={headRef}>
                <table class="wp-table" style={tableStyle}>
                  {cols}
                  <thead>
                    <tr>
                      <th class="wp-cnr">Ngày</th>
                      {ws.map((w) => <th key={w.id} title={`${w.name} — ${money(w.total)}đ cả kỳ`}>{shortName(w.name)}</th>)}
                      <th class="wp-tot">Tổng</th>
                    </tr>
                  </thead>
                </table>
              </div>
              <div class="wp-tbody-scroll" ref={wrapRef}
                onScroll={(e: any) => {
                  const x = e.currentTarget.scrollLeft;
                  _saved = { ym, view, left: x };
                  if (headRef.current) headRef.current.scrollLeft = x;
                  if (footRef.current) footRef.current.scrollLeft = x;
                }}>
              <table class="wp-table" style={tableStyle}>
                {cols}
                <tbody>
                  {data.days.map((d) => (
                    <>
                      <tr key={d.ymd} data-row={d.ymd} class={`${view === "slip" ? "wp-dayrow grouped" : "wp-dayrow"}${activeRow === d.ymd ? " is-active" : ""}`}>
                        <th class="wp-day" title={d.ymd}>
                          <b>{dayNum(d.ymd)}</b> <span class="muted">{dowOf(d.ymd)}</span>
                        </th>
                        {ws.map((w) => {
                          const v = d.cells[String(w.id)] || 0;
                          // view CHI TIẾT: hàng ngày chỉ là TIÊU ĐỀ NHÓM → không tô màu,
                          // để thang màu dành riêng cho các ô phiếu bên dưới cho dễ so
                          // view chi tiết: dấu nằm ở ô PHIẾU bên dưới, hàng ngày chỉ là tiêu đề nhóm
                          const fl = view === "day" ? dayFlag(d, w.id) : "";
                          return (
                            <td key={w.id} class={`wp-cell${flagCls(fl)}`} style={view === "slip" || fl === "open" ? "" : heat(v, data.max_cell)}
                              onClick={() => { setActiveRow(d.ymd); if (v || fl) setCell({ kind: "day", day: d, wid: w.id }); }}
                              title={`${v ? `${w.name} · ${d.ymd} — ${money(v)}đ · bấm xem chi tiết` : ""}${fl ? FLAG_TIP : ""}`}>{fl === "open" ? "!" : k(v)}</td>
                          );
                        })}
                        <td class="wp-tot wp-cell" onClick={() => { setActiveRow(d.ymd); if (d.total) setCell({ kind: "dayTotal", day: d }); }}
                          title={d.total ? "Bấm xem ngày này chia cho thợ nào" : ""}>{k(d.total)}</td>
                      </tr>
                      {/* view CHI TIẾT: mỗi phiếu SX trong ngày là 1 hàng con */}
                      {view === "slip" && d.slips.map((s) => (
                        <tr key={`${d.ymd}-${s.thread_id}`} data-row={`${d.ymd}#${s.thread_id}`}
                          class={activeRow === `${d.ymd}#${s.thread_id}` ? "wp-sliprow is-active" : "wp-sliprow"}>
                          <th class="wp-slip" title={`Phiếu #${s.thread_id}${s.start ? ` · ${s.start}–${s.end || "?"}` : ""}`}>
                            <a href={`#/san_xuat/${s.thread_id}`}>{s.code || "—"}</a>
                            <span class={slipHasOt(s) ? "wp-slip-t ot" : "wp-slip-t"}>{slipSpan(s)}</span>
                          </th>
                          {ws.map((w) => {
                            const v = s.cells[String(w.id)] || 0;
                            const fl = slipFlag(s, w.id);
                            return (
                              <td key={w.id} class={`wp-cell${flagCls(fl)}`} style={fl === "open" ? "" : heat(v, maxSlip)}
                                onClick={() => { setActiveRow(`${d.ymd}#${s.thread_id}`); if (v || fl) setCell({ kind: "slip", day: d, slip: s, wid: w.id }); }}
                                title={`${v ? `${w.name} · ${s.code} — ${money(v)}đ · bấm xem cách tính` : ""}${fl ? FLAG_TIP : ""}`}>{fl === "open" ? "!" : k(v)}</td>
                            );
                          })}
                          <td class="wp-tot">{k(s.total)}</td>
                        </tr>
                      ))}
                    </>
                  ))}
                </tbody>
              </table>
              </div>
              {/* Dòng TỔNG tách thành thanh riêng DÍNH ĐÁY màn hình (trên thanh nav):
                  để trong <tfoot> của bảng thân thì không dính được — .wp-tbody-scroll
                  có overflow-x nên là vùng cuộn riêng, sticky bottom sẽ bám đáy BẢNG
                  chứ không bám đáy màn hình. */}
              <div class="wp-tfoot-bar" ref={footRef}>
                <table class="wp-table" style={tableStyle}>
                  {cols}
                  <tfoot>
                    <tr>
                      <th class="wp-cnr">Tổng</th>
                      {ws.map((w) => <td key={w.id} title={`${w.name} — ${money(w.total)}đ`}>{k(w.total)}</td>)}
                      <td class="wp-tot">{k(data.grand)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          </>
        )}
      {cell && data && <WagePivotCell cell={cell} data={data} onClose={() => setCell(null)} />}
    </div>
  );
}
