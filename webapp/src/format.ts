// Format tiền/ngày kiểu Việt Nam — thuần, dùng khắp các page.

// Bỏ dấu tiếng Việt GIỮ NGUYÊN ĐỘ DÀI (1 ký tự → 1 ký tự) để map vị trí khớp về
// text gốc khi tô sáng. Dùng bảng precomposed (không NFD vì NFD đổi độ dài).
const _VN_FOLD: Record<string, string> = (() => {
  const g: Record<string, string> = {
    a: "àáảãạăằắẳẵặâầấẩẫậ", e: "èéẻẽẹêềếểễệ", i: "ìíỉĩị",
    o: "òóỏõọôồốổỗộơờớởỡợ", u: "ùúủũụưừứửữự", y: "ỳýỷỹỵ", d: "đ",
  };
  const m: Record<string, string> = {};
  for (const base in g) for (const c of g[base]) { m[c] = base; m[c.toUpperCase()] = base; }
  return m;
})();

/** Bỏ dấu + thường hoá, giữ nguyên độ dài chuỗi. */
export function foldVN(s: string): string {
  const src = s || "";
  let out = "";
  for (let i = 0; i < src.length; i++) out += _VN_FOLD[src[i]] ?? src[i].toLowerCase();
  return out;
}

/** Chữ cái đầu tên (avatar tròn khách hàng — CreateOrder/OrderDetail). */
export const initial = (name: string) => ((name || "").trim().charAt(0) || "?").toUpperCase();

// Giá rút gọn cho cột hẹp (preview chia đôi màn): 17000 → "17k", 25500 → "25,5k".
export const moneyK = (v: number) =>
  v >= 1000 && v % 100 === 0 ? `${(v / 1000).toLocaleString("vi-VN")}k` : money(v);

export function money(n: number | string): string {
  const v = typeof n === "string" ? parseInt(n.replace(/\./g, ""), 10) || 0 : n || 0;
  return v.toLocaleString("vi-VN");
}

export function parseMoney(s: string): number {
  return parseInt(String(s).replace(/[^\d]/g, ""), 10) || 0;
}

/** Chỉ giữ chữ số, TRẢ CHUỖI ("1.500.000đ" → "1500000"; "" → ""). Khác parseMoney ở
 *  chỗ giữ được ô rỗng — ô nhập tiền controlled cần phân biệt "chưa gõ" với số 0. */
export const digitsOnly = (s: string) => String(s ?? "").replace(/[^\d]/g, "");

/** ĐỌC LẠI số tiền cho người kiểm tra bằng mắt: 1500000 → "1 triệu 500 nghìn".
 *  Dùng dưới ô nhập tiền (ui/MoneyEntryForm) — chỗ duy nhất bắt được lỗi thừa/thiếu
 *  số 0 trước khi lưu. Số lẻ dưới nghìn đọc thẳng "đồng". */
export function docTien(n: number): string {
  if (!n || n < 0 || !isFinite(n)) return "";
  const tr = Math.floor(n / 1_000_000);
  const ng = Math.floor((n % 1_000_000) / 1000);
  const le = Math.round(n % 1000);
  const parts: string[] = [];
  if (tr) parts.push(`${tr} triệu`);
  if (ng) parts.push(`${ng} nghìn`);
  if (le) parts.push(`${le} đồng`);
  return parts.join(" ");
}

/** Tiền LÀM TRÒN đồng (payroll hay có số lẻ float): 12345.6 → "12.346". */
export const moneyR = (n: number) => money(Math.round(n || 0));
/** moneyR kèm "đ" — nhãn tiền đầy đủ ở các trang lương. */
export const moneyD = (n: number) => moneyR(n) + "đ";

/** Đệm 2 chữ số: 7 → "07". */
export const pad2 = (n: number) => String(n).padStart(2, "0");
/** Date → "YYYY-MM-DD" (giờ máy — dùng cho ô input date / key ngày). */
export const isoDate = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

/** Tháng hiện tại "YYYY-MM" + dịch tháng + nhãn "Tháng M/YYYY" — dùng chung các
 *  trang lương/chấm công (trước đây 4 file tự chép bộ này). */
export const curYM = () => { const d = new Date(); return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`; };
export const shiftYM = (ym: string, d: number) => {
  const [y, m] = ym.split("-").map(Number);
  const dt = new Date(y, m - 1 + d, 1);
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}`;
};
export const ymLabel = (ym: string) => { const [y, m] = ym.split("-"); return `Tháng ${Number(m)}/${y}`; };

/** "YYYY-MM-DD" → "05/07" (ngày gọn trên dòng ứng lương). */
export const dmy = (s?: string) => (s && s.length >= 10 ? `${s.slice(8, 10)}/${s.slice(5, 7)}` : s || "—");
/** Mốc DB "YYYY-MM-DD HH:MM:SS" đã là GIỜ VN (salary_store ghi datetime('now','+7 hours'))
 *  → "18/7 19:25"; chuỗi thiếu → "". Dùng chung trang nhập ứng/phụ cấp + panel bảng lương. */
export const tsLabel = (s?: string) =>
  (s && s.length >= 16 ? `${Number(s.slice(8, 10))}/${Number(s.slice(5, 7))} ${s.slice(11, 16)}` : "");

/** TUẦN LƯƠNG = THỨ 7 tuần trước → THỨ 6 tuần này (đúng 7 ngày). Mốc chốt kỳ =
 *  thứ 6 GẦN NHẤT ĐÃ QUA (hôm nay nếu hôm nay thứ 6) → khoảng ngày không bao giờ
 *  lấn sang ngày chưa làm; bấm ngày thứ 6 (ngày chốt lương) ra đúng tuần vừa xong.
 *  Hai kỳ liên tiếp KHÔNG đè ngày nào (kỳ trước kết thứ 6, kỳ sau mở thứ 7) — đừng
 *  đổi thành 8 ngày, sản lượng ngày giao nhau sẽ được trả lương 2 lần.
 *  `back` = lùi mấy tuần (0 = tuần này, 1 = tuần trước).
 *  Dùng chung #/bao-cao + #/in-luong — đừng chép lại. */
export function payWeek(back = 0, today: Date = new Date()): { from: string; to: string } {
  const end = new Date(today);
  end.setDate(today.getDate() - ((today.getDay() + 2) % 7) - back * 7);
  const start = new Date(end);
  start.setDate(end.getDate() - 6);
  return { from: isoDate(start), to: isoDate(end) };
}

/** Số lượng CÓ THỂ THẬP PHÂN — chấp nhận dấu ',' (VN) hoặc '.' làm phần thập phân.
 *  Trả float, lỗi → 0. Khác parseMoney (ép số nguyên cho tiền đồng). */
export function parseQty(s: string): number {
  return parseFloat(String(s).replace(/,/g, ".").replace(/[^\d.]/g, "")) || 0;
}

/** Hiển thị số lượng trong ô nhập: dấu ',' cho phần thập phân, KHÔNG chấm nghìn
 *  (chấm nghìn sẽ vướng khi gõ). vd 1.5 → "1,5", 12 → "12". */
export function fmtQty(n: number): string {
  return String(n).replace(".", ",");
}

export function timeAgo(epochSec: number): string {
  const diff = Math.floor(Date.now() / 1000) - epochSec;
  if (diff < 60) return "vừa xong";
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
  return new Date(epochSec * 1000).toLocaleDateString("vi-VN");
}

/** Chuẩn hoá mọi kiểu thời gian về mili-giây. Chấp nhận: epoch giây/ms, chuỗi
 *  ISO (có Z), hoặc 'YYYY-MM-DD HH:MM:SS' (server lưu UTC, không tz → coi là UTC). */
function toMs(at: any): number | null {
  if (at == null || at === "") return null;
  if (typeof at === "number") return at < 1e12 ? at * 1000 : at;
  let s = String(at).trim();
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(s)) s = s.replace(" ", "T") + "Z";
  const t = Date.parse(s);
  return isNaN(t) ? null : t;
}

/** Hiển thị thời gian: tương đối nếu ≤7 ngày, ngược lại ngày/giờ tuyệt đối theo
 *  giờ Việt Nam (Asia/Ho_Chi_Minh) — không phụ thuộc múi giờ thiết bị. */
export function fmtTime(at: any): string {
  const ms = toMs(at);
  if (ms == null) return "";
  const sec = Math.floor((Date.now() - ms) / 1000);
  if (sec < 0) return absVN(ms);
  if (sec < 60) return "vừa xong";
  if (sec < 3600) return `${Math.floor(sec / 60)} phút trước`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} giờ trước`;
  if (sec < 7 * 86400) return `${Math.floor(sec / 86400)} ngày trước`;
  return absVN(ms);
}

function absVN(ms: number): string {
  return new Date(ms).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

/** CHỈ giờ:phút theo giờ VN — "HH:MM". Rỗng nếu không parse được.
 *  Dùng cho "lúc HH:MM" ở báo cáo ảnh theo ngày. KHÔNG được cắt chuỗi kiểu
 *  String(at).slice(11,16): server lưu UTC nên cắt thô ra sai 7 tiếng. */
export function fmtHourVN(at: any): string {
  // 0 = "chưa có giờ" (ảnh cũ lưu trước khi có created_at), KHÔNG phải mốc 1970
  if (!at) return "";
  const ms = toMs(at);
  if (ms == null) return "";
  return new Date(ms).toLocaleTimeString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

/** Ngày+giờ tuyệt đối theo giờ VN: "dd/mm/yyyy HH:MM". Rỗng nếu không parse được. */
export function fmtDateTimeVN(at: any): string {
  const ms = toMs(at);
  if (ms == null) return "";
  return new Date(ms).toLocaleString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/** Hiển thị ngày giao ('YYYY-MM-DDTHH:MM') → 'DD/MM' (nếu giờ 00:00) hoặc 'DD/MM HH:MM'.
 *  Rỗng/không hợp lệ → "". Dùng cho badge card + trang chi tiết. */
export function fmtNgayGiao(v?: string | null): string {
  const s = (v || "").trim();
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
  if (!m) return "";
  const [, , mo, d, hh, mm] = m;
  const date = `${d}/${mo}`;
  return hh && !(hh === "00" && mm === "00") ? `${date} ${hh}:${mm}` : date;
}

/** Mốc thời gian nằm trong `withinSec` giây gần đây (và không ở tương lai). */
export function isRecent(at: any, withinSec: number): boolean {
  const ms = toMs(at);
  if (ms == null) return false;
  const d = Date.now() - ms;
  return d >= 0 && d < withinSec * 1000;
}

/** Thời gian tương đối tiếng Việt (luôn dạng "… trước"), kể cả mốc xa. */
export function fmtRelative(at: any): string {
  const ms = toMs(at);
  if (ms == null) return "";
  const sec = Math.floor((Date.now() - ms) / 1000);
  if (sec < 0) return "";
  if (sec < 60) return "vừa xong";
  if (sec < 3600) return `${Math.floor(sec / 60)} phút trước`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} giờ trước`;
  if (sec < 30 * 86400) return `${Math.floor(sec / 86400)} ngày trước`;
  if (sec < 365 * 86400) return `${Math.floor(sec / (30 * 86400))} tháng trước`;
  return `${Math.floor(sec / (365 * 86400))} năm trước`;
}

/** Key ngày YYYY-MM-DD từ timestamp ISO — để nhóm list theo ngày. */
export const dayKey = (at?: string) => (at || "").slice(0, 10);

const _WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
/** Nhãn nhóm ngày chuẩn toàn app: "Hôm nay · T5 17/07" / "Hôm qua · …" /
 *  "T2 14/07/2026" (ngày xa kèm năm). Nhận key từ dayKey(). */
export function dayLabel(k: string): string {
  if (!k) return "Không rõ ngày";
  const d = new Date(k);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - d.getTime()) / 86400000);
  const lbl = `${_WD[d.getDay()]} ${k.slice(8)}/${k.slice(5, 7)}`;
  if (diff === 0) return `Hôm nay · ${lbl}`;
  if (diff === 1) return `Hôm qua · ${lbl}`;
  return `${lbl}/${k.slice(0, 4)}`;
}

/** Tổng tiền hàng từ invoice (sl × price). SL có thể LẺ (3,5 thùng) — parseInt
 *  cắt mất phần lẻ làm tổng/nợ hiển thị thiếu so với server. */
export function invoiceTotal(invoice: any[]): number {
  return (invoice || []).reduce((sum, it) => {
    const price = parseInt(it.price, 10) || 0;
    const rawSl = it.sl ?? it.quantity;
    const sl = typeof rawSl === "number" ? rawSl : parseQty(String(rawSl ?? ""));
    return sum + Math.round(price * (Number.isFinite(sl) ? sl : 0));
  }, 0);
}

/** Tổng đã trả từ payments. */
export function paidTotal(payments: any[]): number {
  return (payments || []).reduce((sum, p) => sum + (parseInt(p.amount, 10) || 0), 0);
}
