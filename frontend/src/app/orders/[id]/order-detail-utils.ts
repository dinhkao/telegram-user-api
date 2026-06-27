export function fmtVND(val: unknown): string {
  if (!val && val !== 0) return '—';
  const n = typeof val === 'string' ? parseInt(val.replace(/\./g, '')) : Number(val);
  if (isNaN(n) || n === 0) return '—';
  return n.toLocaleString('vi-VN') + '₫';
}

export function toVnTime(utcStr: string): string {
  if (!utcStr) return '';
  const m = utcStr.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/);
  if (!m) return utcStr;
  let h = +m[4] + 7;
  let d = +m[3];
  const mo = +m[2] - 1;
  if (h >= 24) {
    h -= 24;
    d++;
  }
  return `${String(h).padStart(2, '0')}:${m[5]} ${String(d).padStart(2, '0')}/${String(mo + 1).padStart(2, '0')}`;
}

export const TASKS = ['ban_hd', 'soan_hang', 'giao_hang', 'nop_tien', 'nhan_tien'] as const;
export const TASK_LABELS: Record<string, string> = { ban_hd: 'Bán HĐ', soan_hang: 'Soạn hàng', giao_hang: 'Giao hàng', nop_tien: 'Nộp tiền', nhan_tien: 'Nhận tiền' };
