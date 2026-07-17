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

/** Tổng tiền hàng từ invoice (sl × price). */
export function invoiceTotal(invoice: any[]): number {
  return (invoice || []).reduce((sum, it) => sum + (parseInt(it.price, 10) || 0) * (parseInt(it.sl ?? it.quantity, 10) || 0), 0);
}

/** Tổng đã trả từ payments. */
export function paidTotal(payments: any[]): number {
  return (payments || []).reduce((sum, p) => sum + (parseInt(p.amount, 10) || 0), 0);
}
