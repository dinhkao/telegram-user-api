// SẮP XẾP bảng lương tháng (#/luong-thang) + ĐỊNH NGHĨA 14 CỘT dùng chung cho header.
// Bấm tiêu đề cột: lần 1 sắp (cột số → LỚN trước, cột chữ → A→Z), lần 2 đảo chiều,
// lần 3 về thứ tự mặc định của server (sort_order hồ sơ thợ). Lựa chọn nhớ trong
// localStorage nên mở lại vẫn giữ.
// ⚠ THỨ TỰ `COLS` phải khớp thứ tự <td> ở thân bảng LẪN mảng COL_EM (colgroup) trong
// MonthlyPayroll.tsx — lệch 1 ô là cả bảng lệch cột.
import type { PayrollRow } from "../api";

export type SortKey = "name" | "type" | "weekly" | "moc" | "cong"
  | "tc" | "luong_tg" | "luong_sp" | "pc" | "cc" | "vs" | "cho_hang" | "ung" | "bhxh" | "net";
export type Sort = { key: SortKey; dir: 1 | -1 };

export const COLS: { key: SortKey; label: string; title: string; num: boolean }[] = [
  { key: "name", label: "Thợ", title: "Tên thợ — bấm để sắp A→Z", num: false },
  { key: "type", label: "Loại", title: "Loại lương (SP → TG → TG*)", num: true },
  { key: "weekly", label: "Tuần", title: "Nhận lương tuần — áp cho cả lương SP lẫn lương thời gian; bật thì lương tháng coi như đã trả, trừ hết vào ứng", num: true },
  { key: "moc", label: "Mốc", title: "Mốc lương tháng (thợ lương thời gian)", num: true },
  { key: "cong", label: "Công", title: "Ngày công", num: true },
  { key: "tc", label: "TC", title: "Giờ tăng ca", num: true },
  { key: "luong_tg", label: "Lương công+TC", title: "Lương THỜI GIAN = lương ngày công + lương tăng ca", num: true },
  { key: "luong_sp", label: "Lương SP", title: "Lương SẢN PHẨM (tự tính từ báo cáo sản xuất)", num: true },
  { key: "pc", label: "P.cấp", title: "Phụ cấp tháng", num: true },
  { key: "cc", label: "Ch.cần", title: "Thưởng chuyên cần — cố định, bấm để bật/tắt (chỉ tháng này)", num: true },
  { key: "vs", label: "Vệ sinh", title: "Thưởng vệ sinh — 12.000đ × ngày công, bấm để bật/tắt (chỉ tháng này)", num: true },
  { key: "cho_hang", label: "Chờ hàng", title: "Lương chờ hàng — bấm ô để nhập số tiền (chỉ tháng này)", num: true },
  { key: "ung", label: "Ứng", title: "Đã ứng", num: true },
  { key: "bhxh", label: "BHXH", title: "Trừ BHXH hằng tháng (BHXH/BHYT/BHTN phần NV đóng)", num: true },
  { key: "net", label: "Lãnh", title: "Thực lãnh = lương + phụ cấp + thưởng + chờ hàng − ứng − BHXH", num: true },
];

/** Giá trị đem so của 1 dòng theo cột. Cột chữ trả string, còn lại trả số. */
function val(r: PayrollRow, key: SortKey): number | string {
  switch (key) {
    case "name": return r.name || "";
    case "type": return r.wage_type === "product" ? 0 : r.wage_type === "time" ? 1 : 2;
    case "weekly": return r.weekly ? 1 : 0;
    case "moc": return r.monthly_salary || 0;
    case "cong": return r.cong || 0;
    case "tc": return r.ot_gio || 0;
    case "luong_tg": return r.luong_tg || 0;
    case "luong_sp": return r.luong_sp || 0;
    case "pc": return r.phu_cap || 0;
    case "cc": return r.thuong_cc || 0;
    case "vs": return r.thuong_vs || 0;
    case "cho_hang": return r.cho_hang || 0;
    case "ung": return r.ung || 0;
    case "bhxh": return r.bhxh || 0;
    case "net": return r.thuc_lanh || 0;
  }
}

/** Bản SAO đã sắp (không đụng mảng gốc). s = null → giữ nguyên thứ tự server. */
export function sortRows(rows: PayrollRow[], s: Sort | null): PayrollRow[] {
  if (!s) return rows;
  const out = rows.slice();
  out.sort((a, b) => {
    const x = val(a, s.key), y = val(b, s.key);
    const c = typeof x === "string"
      ? String(x).localeCompare(String(y), "vi")
      : (x as number) - (y as number);
    // hoà thì xếp theo TÊN (luôn A→Z) để thứ tự ổn định, khỏi nhảy lung tung
    return c ? c * s.dir : a.name.localeCompare(b.name, "vi");
  });
  return out;
}

/** Bấm 1 cột → trạng thái kế tiếp: sắp → đảo chiều → bỏ sắp. */
export function nextSort(cur: Sort | null, key: SortKey, num: boolean): Sort | null {
  const first: 1 | -1 = num ? -1 : 1;        // cột số: lớn trước; cột chữ: A→Z
  if (!cur || cur.key !== key) return { key, dir: first };
  if (cur.dir === first) return { key, dir: (first === 1 ? -1 : 1) };
  return null;
}

const KEY = "payroll_sort";
export function loadSort(): Sort | null {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "null");
    return s && COLS.some((c) => c.key === s.key) && (s.dir === 1 || s.dir === -1) ? s : null;
  } catch { return null; }
}
export function saveSort(s: Sort | null): void {
  try {
    if (s) localStorage.setItem(KEY, JSON.stringify(s));
    else localStorage.removeItem(KEY);
  } catch { /**/ }
}
