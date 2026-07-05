// Báo cáo sản xuất theo thợ — NHẬP TRỰC TIẾP vào bảng (thêm/xoá dòng), tự tính số
// mâm + tổng theo số cây 1 mâm của SP (slip.sp_mam). Lưu → sinh text ";" rồi gửi
// endpoint cũ (parse + compute + đẩy Google Sheet) nên không cần dán từ sheet nữa —
// vẫn giữ mục "dán từ sheet" làm phương án phụ. Data: saveProductionReport.
import { useEffect, useMemo, useState } from "preact/hooks";
import { saveProductionReport, soVN, type ProdSlip, type ProdReport } from "../api";

type Wrow = { name: string; gach: string; tru: string; le: string; note: string };

const _num = (s: string): number => {
  const n = parseFloat((s || "").trim().replace(",", "."));
  return isFinite(n) ? n : 0;
};
const round2 = (x: number) => Math.round(x * 100) / 100;
const todayVN = (): string => {
  const d = new Date();
  return `${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`;
};
const rowsFromReport = (rep: ProdReport | null): Wrow[] =>
  rep?.rows?.length
    ? rep.rows.map((r) => ({
        name: r.name,
        gach: r.so_gach ? String(r.so_gach) : "",
        tru: r.so_tru ? String(r.so_tru) : "",
        le: r.so_cay_le ? String(r.so_cay_le) : "",
        note: r.note || "",
      }))
    : [{ name: "", gach: "", tru: "", le: "", note: "" }];

export function ProductionReport({ threadId, slip }: { threadId: string; slip: ProdSlip }) {
  const bang = slip.bang as ProdReport | null;
  const [report, setReport] = useState<ProdReport | null>(bang || null);
  const [wrows, setWrows] = useState<Wrow[]>(rowsFromReport(bang || null));
  const [date, setDate] = useState<string>((bang as any)?.date || todayVN());
  const [start, setStart] = useState<string>((bang as any)?.start || "");
  const [end, setEnd] = useState<string>((bang as any)?.end || "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [open, setOpen] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [text, setText] = useState("");

  // Đồng bộ khi slip.bang đổi (realtime: người khác lưu báo cáo)
  useEffect(() => {
    const rep = (slip.bang as ProdReport) || null;
    setReport(rep);
    setWrows(rowsFromReport(rep));
    if ((rep as any)?.date) setDate((rep as any).date);
    if ((rep as any)?.start) setStart((rep as any).start);
    if ((rep as any)?.end) setEnd((rep as any).end);
  }, [slip.bang]);

  const scm = Number(report?.so_cay_1_mam || slip.sp_mam || 0);
  const calc = (r: Wrow) => {
    const g = _num(r.gach), t = _num(r.tru), l = _num(r.le);
    const soMam = Math.max(g * 5 - t - (l > 0 ? 1 : 0), 0);   // giống compute_report
    const tong = scm > 0 ? round2(scm * soMam + l) : 0;
    return { soMam, tong };
  };
  const grand = useMemo(() => round2(wrows.reduce((s, r) => s + calc(r).tong, 0)), [wrows, scm]);

  const setRow = (i: number, patch: Partial<Wrow>) => setWrows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const addRow = () => setWrows((rs) => [...rs, { name: "", gach: "", tru: "", le: "", note: "" }]);
  const delRow = (i: number) => setWrows((rs) => (rs.length > 1 ? rs.filter((_, k) => k !== i) : rs));

  // Sinh text ";" 20 cột (CODE@13, date@14, start@18, end@19) + header để parser bỏ qua
  const buildText = (): string => {
    const CODE = (slip.sp_name || "").toUpperCase();
    const lines = wrows
      .filter((r) => r.name.trim())
      .map((r) => {
        const { soMam, tong } = calc(r);
        const c = Array(20).fill("");
        c[0] = r.name.trim(); c[1] = r.gach.trim(); c[2] = r.tru.trim(); c[3] = r.le.trim(); c[4] = r.note.trim();
        c[5] = tong ? String(tong) : "";   // tổng (fallback khi server chưa biết số cây 1 mâm)
        c[13] = CODE; c[14] = date.trim();
        c[17] = soMam ? String(soMam) : ""; // số mâm ĐÃ tính (col 17 = nguồn chuẩn của server)
        c[18] = start.trim(); c[19] = end.trim();
        return c.join(";");
      });
    return ["thợ;gạch;trừ;lẻ;ghi chú", ...lines].join("\n");
  };

  const doSave = async (payload: string) => {
    setBusy(true); setMsg("");
    try {
      const r = await saveProductionReport(threadId, payload);
      setReport(r);
      setWrows(rowsFromReport(r));
      const s = r.sheet;
      if (s?.ok) setMsg(`✅ Đã lưu + đẩy Google Sheet — tab ${s.tab}, ${s.rows} dòng${s.replaced ? " (ghi đè)" : ""}.`);
      else if (s?.disabled) setMsg("✅ Đã lưu. ⚠️ Chưa đẩy Sheet: thiếu credentials.");
      else setMsg(`✅ Đã lưu. ❌ Đẩy Sheet lỗi: ${s?.error || "?"}`);
    } catch (e: any) {
      setMsg(e?.message || "Lỗi lưu báo cáo");
    } finally {
      setBusy(false);
    }
  };
  const saveTable = () => {
    if (!wrows.some((r) => r.name.trim())) { setMsg("Chưa nhập thợ nào."); return; }
    doSave(buildText());
  };

  return (
    <section class="card">
      <label class="card-label" onClick={() => setOpen((v) => !v)} style={{ cursor: "pointer" }}>
        📊 Báo cáo theo thợ {open ? "▲" : "▼"}
      </label>

      {!open && report && report.rows?.length > 0 && (
        <div class="muted small">Tổng: <b>{soVN(report.grand_total)}</b> · {report.rows.length} thợ</div>
      )}

      {open && (
        <>
          <div class="prod-report-meta">
            {slip.sp_name && <span>📦 {slip.sp_name}</span>}
            {scm > 0 && <span>🌿 {scm}/mâm</span>}
            <label>📅 <input class="wr-meta" value={date} onInput={(e: any) => setDate(e.target.value)} placeholder="d/m/yyyy" /></label>
            <label>🕒 <input class="wr-meta wr-time" value={start} onInput={(e: any) => setStart(e.target.value)} placeholder="bắt đầu" />–<input class="wr-meta wr-time" value={end} onInput={(e: any) => setEnd(e.target.value)} placeholder="xong" /></label>
          </div>
          {scm <= 0 && <div class="prod-save-msg">⚠️ SP chưa có số cây 1 mâm — chọn mã SP để tính tổng.</div>}

          <div class="prod-report-scroll">
            <table class="prod-report-table wr-edit">
              <thead>
                <tr><th>Thợ</th><th>Gạch</th><th>Trừ</th><th>Lẻ</th><th>Mâm</th><th>Tổng</th><th>Ghi chú</th><th></th></tr>
              </thead>
              <tbody>
                {wrows.map((r, i) => {
                  const c = calc(r);
                  return (
                    <tr key={i} class={c.tong > 0 ? "" : "prod-row-off"}>
                      <td><input class="wr-in wr-name" value={r.name} onInput={(e: any) => setRow(i, { name: e.target.value })} placeholder="Tên" /></td>
                      <td><input class="wr-in wr-num" inputMode="decimal" value={r.gach} onInput={(e: any) => setRow(i, { gach: e.target.value })} /></td>
                      <td><input class="wr-in wr-num" inputMode="decimal" value={r.tru} onInput={(e: any) => setRow(i, { tru: e.target.value })} /></td>
                      <td><input class="wr-in wr-num" inputMode="decimal" value={r.le} onInput={(e: any) => setRow(i, { le: e.target.value })} /></td>
                      <td class="wr-calc">{soVN(c.soMam)}</td>
                      <td class="wr-calc strong">{soVN(c.tong)}</td>
                      <td><input class="wr-in wr-note" value={r.note} onInput={(e: any) => setRow(i, { note: e.target.value })} placeholder="—" /></td>
                      <td><button class="btn small wr-del" title="Xoá dòng" onClick={() => delRow(i)}>✕</button></td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr><td colSpan={5}>TỔNG CỘNG</td><td class="strong">{soVN(grand)}</td><td colSpan={2}></td></tr>
              </tfoot>
            </table>
          </div>

          <div class="row">
            <button class="btn" onClick={addRow}>➕ Thêm thợ</button>
            <button class="btn primary" disabled={busy} onClick={saveTable}>💾 Lưu báo cáo</button>
          </div>
          {msg && <div class="prod-save-msg">{msg}</div>}

          <label class="card-label small" onClick={() => setPasteOpen((v) => !v)} style={{ cursor: "pointer", marginTop: "8px" }}>
            📋 Hoặc dán từ Google Sheet {pasteOpen ? "▲" : "▼"}
          </label>
          {pasteOpen && (
            <>
              <textarea class="prod-report-input" rows={4} value={text} onInput={(e) => setText((e.target as HTMLTextAreaElement).value)} placeholder="Dán dữ liệu ; (mỗi thợ 1 dòng)…" />
              <div class="row"><button class="btn primary" disabled={busy} onClick={() => text.trim() && doSave(text)}>💾 Lưu từ dán</button></div>
            </>
          )}
        </>
      )}
    </section>
  );
}
