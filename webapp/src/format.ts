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

/** Tổng tiền hàng từ invoice (sl × price). */
export function invoiceTotal(invoice: any[]): number {
  return (invoice || []).reduce((sum, it) => sum + (parseInt(it.price, 10) || 0) * (parseInt(it.sl ?? it.quantity, 10) || 0), 0);
}

/** Tổng đã trả từ payments. */
export function paidTotal(payments: any[]): number {
  return (payments || []).reduce((sum, p) => sum + (parseInt(p.amount, 10) || 0), 0);
}
