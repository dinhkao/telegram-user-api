// Format tiền/ngày kiểu Việt Nam — thuần, dùng khắp các page.

export function money(n: number | string): string {
  const v = typeof n === "string" ? parseInt(n.replace(/\./g, ""), 10) || 0 : n || 0;
  return v.toLocaleString("vi-VN");
}

export function parseMoney(s: string): number {
  return parseInt(String(s).replace(/[^\d]/g, ""), 10) || 0;
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

/** Tổng tiền hàng từ invoice (sl × price). */
export function invoiceTotal(invoice: any[]): number {
  return (invoice || []).reduce((sum, it) => sum + (parseInt(it.price, 10) || 0) * (parseInt(it.sl ?? it.quantity, 10) || 0), 0);
}

/** Tổng đã trả từ payments. */
export function paidTotal(payments: any[]): number {
  return (payments || []).reduce((sum, p) => sum + (parseInt(p.amount, 10) || 0), 0);
}
