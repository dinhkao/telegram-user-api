import type { OrderSummary } from '@/lib/api';

export type OrderDebtInfo = { text: string; cls: string };

export function fmtVND(val: string): string {
  return parseInt(String(val).replace(/\./g, '')).toLocaleString('vi-VN') + '₫';
}

export function relativeTime(dateStr: string): string {
  if (!dateStr) return '';
  const m = dateStr.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})/);
  if (!m) return '';
  const then = new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5]);
  const diffMin = Math.floor((Date.now() - then.getTime()) / 60000);
  if (diffMin < 1) return 'Vừa xong';
  if (diffMin < 60) return diffMin + ' phút';
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return diffH + ' giờ';
  const diffD = Math.floor(diffH / 24);
  if (diffD === 1) return 'Hôm qua';
  if (diffD < 7) return diffD + ' ngày';
  if (diffD < 30) return Math.floor(diffD / 7) + ' tuần';
  return Math.floor(diffD / 30) + ' tháng';
}

export function debtInfo(o: OrderSummary): OrderDebtInfo {
  const raw = o.total ? parseInt(String(o.total).replace(/\./g, '')) : 0;
  if (o.nhan_tien_note === 'gtr') return { text: 'Gửi toa rồi', cls: 'text-amber-600' };
  if (raw > 0 && o.remaining === 0) return { text: '✅', cls: 'text-emerald-600' };
  if (raw > 0 && o.paid > 0) return { text: o.remaining.toLocaleString('vi-VN') + '₫', cls: 'text-amber-600' };
  if (raw > 0) return { text: o.remaining.toLocaleString('vi-VN') + '₫', cls: 'text-red-600' };
  return { text: '—', cls: 'text-muted-foreground' };
}
