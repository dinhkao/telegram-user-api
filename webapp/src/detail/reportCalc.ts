// Tính báo cáo thợ (mâm/tổng) — DÙNG CHUNG cho trang SỬA (ProductionReportEdit) và
// phần XEM (ProductionReport hiện bản nháp realtime). Logic = sheet "Nhập kẹo":
//   mâm = mâm-đè ?? gạch×5 − trừ − (lẻ>0?1:0);  tổng = SP-đè ?? scm×mâm + lẻ.
// Ô đè rỗng = không đè (0 VẪN là đè, như ISBLANK). Giữ 1 nguồn để 2 nơi không lệch.

// 1 dòng thợ đang gõ (giá trị thô dạng chuỗi). Khớp draft phát qua report_draft.
export type Wrow = { name: string; gach: string; tru: string; le: string; note: string; spDe: string; mamDe: string };

export const rNum = (s: string): number => { const n = parseFloat((s || "").trim().replace(",", ".")); return isFinite(n) ? n : 0; };
export const round2 = (x: number) => Math.round(x * 100) / 100;

export function calcRow(r: Wrow, scm: number) {
  const g = rNum(r.gach), t = rNum(r.tru), l = rNum(r.le);
  const mamDeSet = (r.mamDe || "").trim() !== "", spDeSet = (r.spDe || "").trim() !== "";
  const soMam = mamDeSet ? rNum(r.mamDe) : Math.max(g * 5 - t - (l > 0 ? 1 : 0), 0);
  const tong = spDeSet ? round2(rNum(r.spDe)) : scm > 0 ? round2(scm * soMam + l) : 0;
  return { soMam, tong, mamDeSet, spDeSet };
}

// Bản nháp (Wrow[]) → dòng hiển thị giống ProdReport.rows để render bảng ở phần XEM.
export function draftToRows(wrows: Wrow[], scm: number) {
  return (wrows || []).map((r) => {
    const c = calcRow(r, scm);
    return {
      name: r.name || "", so_gach: rNum(r.gach), so_tru: rNum(r.tru), so_cay_le: rNum(r.le),
      so_mam: c.soMam, tong_calc: c.tong, note: r.note || "",
      mam_de: c.mamDeSet ? rNum(r.mamDe) : null, sp_de: c.spDeSet ? round2(rNum(r.spDe)) : null,
    };
  });
}
